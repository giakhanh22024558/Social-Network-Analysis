import os
import json
import random
from typing import List
from neo4j import GraphDatabase

# --- cấu hình Neo4j (chỉnh theo máy bạn hoặc dùng env) ---
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456aA@")

# --- cấu hình file đầu ra ---
BASE_DIR = os.path.dirname(__file__)
OUTPUT_FILE = os.path.join(BASE_DIR, "twohop_questions_from_json.json")
MAX_EXAMPLES = 20

def run_query(driver, cypher, params=None):
    with driver.session() as session:
        return [dict(rec) for rec in session.run(cypher, params or {})]

def collect_examples(driver) -> List[dict]:
    examples = []
    seen = set()

    # 1) Director: Person -> ACTED_IN -> Film <- DIRECTED <- Director
    q_director = """
    MATCH (p:Person)-[:ACTED_IN]->(f:Film)<-[:DIRECTED]-(d:Person)
    WHERE p.name IS NOT NULL AND f.title IS NOT NULL AND d.name IS NOT NULL
    RETURN DISTINCT p.name AS person, f.title AS film, d.name AS director
    LIMIT 200
    """
    for r in run_query(driver, q_director):
        uid = (r["person"].lower(), r["film"].lower(), "director")
        if uid in seen: continue
        seen.add(uid)
        examples.append({
            "question_vi": f"Ai là đạo diễn phim {r['film']} mà {r['person']} đóng?",
            "template": "person->ACTED_IN->film<-DIRECTED<-director",
            "subject": r["person"],
            "intermediate": r["film"],
            "object": r["director"],
            "cypher_answer": "MATCH (p:Person {name:$person})-[:ACTED_IN]->(f:Film {title:$film})<-[:DIRECTED]-(d:Person) RETURN d.name AS answer"
        })
        if len(examples) >= MAX_EXAMPLES: return examples

    # 2) Producer: Person -> ACTED_IN -> Film <- PRODUCED <- Producer
    q_producer = """
    MATCH (p:Person)-[:ACTED_IN]->(f:Film)<-[:PRODUCED]-(pr:Person)
    WHERE p.name IS NOT NULL AND f.title IS NOT NULL AND pr.name IS NOT NULL
    RETURN DISTINCT p.name AS person, f.title AS film, pr.name AS producer
    LIMIT 200
    """
    for r in run_query(driver, q_producer):
        uid = (r["person"].lower(), r["film"].lower(), "producer")
        if uid in seen: continue
        seen.add(uid)
        examples.append({
            "question_vi": f"Ai là nhà sản xuất phim {r['film']} mà {r['person']} đóng?",
            "template": "person->ACTED_IN->film<-PRODUCED<-producer",
            "subject": r["person"],
            "intermediate": r["film"],
            "object": r["producer"],
            "cypher_answer": "MATCH (p:Person {name:$person})-[:ACTED_IN]->(f:Film {title:$film})<-[:PRODUCED]-(pr:Person) RETURN pr.name AS answer"
        })
        if len(examples) >= MAX_EXAMPLES: return examples

    # 3) Co-actor: Person -> ACTED_IN -> Film <- ACTED_IN <- CoActor
    q_coactor = """
    MATCH (p:Person)-[:ACTED_IN]->(f:Film)<-[:ACTED_IN]-(co:Person)
    WHERE p.name IS NOT NULL AND f.title IS NOT NULL AND co.name IS NOT NULL AND co.name <> p.name
    RETURN DISTINCT p.name AS person, f.title AS film, co.name AS coactor
    LIMIT 400
    """
    for r in run_query(driver, q_coactor):
        uid = (r["person"].lower(), r["film"].lower(), "coactor", r["coactor"].lower())
        if uid in seen: continue
        seen.add(uid)
        examples.append({
            "question_vi": f"Ai là diễn viên cùng đóng phim {r['film']} với {r['person']}?",
            "template": "person->ACTED_IN->film<-ACTED_IN<-coactor",
            "subject": r["person"],
            "intermediate": r["film"],
            "object": r["coactor"],
            "cypher_answer": "MATCH (p:Person {name:$person})-[:ACTED_IN]->(f:Film {title:$film})<-[:ACTED_IN]-(co:Person) WHERE co.name <> $person RETURN co.name AS answer"
        })
        if len(examples) >= MAX_EXAMPLES: return examples

    # 4) Family two-hop examples using KEY_MAP relations: child->parent->spouse
    q_spouse_of_parent = """
    MATCH (c:Person)-[:IS_CHILD_OF]->(parent:Person)-[:IS_SPOUSE_OF]->(sp:Person)
    WHERE c.name IS NOT NULL AND parent.name IS NOT NULL AND sp.name IS NOT NULL
    RETURN DISTINCT c.name AS child, parent.name AS parent, sp.name AS spouse
    LIMIT 200
    """
    for r in run_query(driver, q_spouse_of_parent):
        uid = (r["child"].lower(), "spouse_of_parent", r["spouse"].lower())
        if uid in seen: continue
        seen.add(uid)
        examples.append({
            "question_vi": f"Ai là vợ/chồng của {r['parent']} (cha/mẹ của {r['child']})?",
            "template": "child->IS_CHILD_OF->parent->IS_SPOUSE_OF->spouse",
            "subject": r["child"],
            "intermediate": r["parent"],
            "object": r["spouse"],
            "cypher_answer": "MATCH (c:Person {name:$child})-[:IS_CHILD_OF]->(parent:Person)-[:IS_SPOUSE_OF]->(sp:Person) RETURN sp.name AS answer"
        })
        if len(examples) >= MAX_EXAMPLES: return examples

    # 5) Sibling's spouse: person->IS_SIBLING_OF->sibling->IS_SPOUSE_OF->spouse
    q_sibling_spouse = """
    MATCH (p:Person)-[:IS_SIBLING_OF]->(s:Person)-[:IS_SPOUSE_OF]->(sp:Person)
    WHERE p.name IS NOT NULL AND s.name IS NOT NULL AND sp.name IS NOT NULL
    RETURN DISTINCT p.name AS person, s.name AS sibling, sp.name AS spouse
    LIMIT 200
    """
    for r in run_query(driver, q_sibling_spouse):
        uid = (r["person"].lower(), "sibling_spouse", r["spouse"].lower())
        if uid in seen: continue
        seen.add(uid)
        examples.append({
            "question_vi": f"Ai là vợ/chồng của anh/chị/em {r['sibling']} (anh/chị/em của {r['person']})?",
            "template": "person->IS_SIBLING_OF->sibling->IS_SPOUSE_OF->spouse",
            "subject": r["person"],
            "intermediate": r["sibling"],
            "object": r["spouse"],
            "cypher_answer": "MATCH (p:Person {name:$person})-[:IS_SIBLING_OF]->(s:Person)-[:IS_SPOUSE_OF]->(sp:Person) RETURN sp.name AS answer"
        })
        if len(examples) >= MAX_EXAMPLES: return examples

    return examples

def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        examples = collect_examples(driver)
    except Exception as e:
        print("Lỗi khi truy vấn Neo4j:", e)
        driver.close()
        return

    if not examples:
        print("Không tìm thấy ví dụ two-hop dựa trên các quan hệ có sẵn.")
        driver.close()
        return

    # trim and shuffle for variability
    random.shuffle(examples)
    examples = examples[:MAX_EXAMPLES]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(examples, f, ensure_ascii=False, indent=2)

    print(f"Đã tạo {len(examples)} câu hỏi two-hop -> {OUTPUT_FILE}")
    driver.close()

if __name__ == "__main__":
    main()