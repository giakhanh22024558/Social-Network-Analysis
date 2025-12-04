import os
import json
from graphdatascience import GraphDataScience

# Cấu hình (tùy chỉnh qua env)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456aA@")

GRAPH_NAME = "prGraph"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "pagerank_top20.json")

# Các loại quan hệ bạn đã import (từ KEY_MAP)
RELATION_TYPES = {
    "ACTED_IN": {"orientation": "UNDIRECTED"},
    "DIRECTED": {"orientation": "UNDIRECTED"},
    "PRODUCED": {"orientation": "UNDIRECTED"},
    "IS_CHILD_OF": {"orientation": "UNDIRECTED"},
    "IS_SPOUSE_OF": {"orientation": "UNDIRECTED"},
    "IS_PARTNER_OF": {"orientation": "UNDIRECTED"},
    "IS_SIBLING_OF": {"orientation": "UNDIRECTED"},
    "IS_PARENT_OF": {"orientation": "UNDIRECTED"},
    "HAS_GRANDPARENT_OF": {"orientation": "UNDIRECTED"},
}

def _rel_map_to_cypher_map(rel_map: dict) -> str:
    # convert Python dict to a Cypher map literal with bare relationship type keys
    parts = []
    for k, v in rel_map.items():
        orient = v.get("orientation", "UNDIRECTED")
        parts.append(f"{k}: {{orientation: '{orient}'}}")
    return "{" + ", ".join(parts) + "}"

def main():
    gds = GraphDataScience(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # 1) Drop existing projection nếu đã tồn tại
    try:
        exists_df = gds.run_cypher(f"CALL gds.graph.exists('{GRAPH_NAME}') YIELD exists")
        if not exists_df.empty and exists_df.loc[0, "exists"]:
            gds.run_cypher(f"CALL gds.graph.drop('{GRAPH_NAME}') YIELD graphName")
    except Exception:
        pass

    # 2) Tạo projection từ label Person + Film và các loại quan hệ đã import
    try:
        rel_map_cypher = _rel_map_to_cypher_map(RELATION_TYPES)
        gds.run_cypher(f"""
        CALL gds.graph.project(
          '{GRAPH_NAME}',
          ['Person','Film'],
          {rel_map_cypher}
        )
        """)
    except Exception as e:
        print("Không thể project graph bằng nodeLabels+relTypes, thử project.cypher fallback:", e)
        # fallback: cypher projection (project tất cả nodes/edges) - dùng elementId/id depending on Neo4j version
        gds.run_cypher(f"""
        CALL gds.graph.project.cypher(
          '{GRAPH_NAME}',
          'MATCH (n) RETURN elementId(n) AS id',
          'MATCH (a)-[r]->(b) RETURN elementId(a) AS source, elementId(b) AS target'
        )
        """)

    # 3) Chạy PageRank (stream) và ghi kết quả vào thuộc tính node (pagerank)
    try:
        gds.run_cypher(f"""
        CALL gds.pageRank.stream('{GRAPH_NAME}')
        YIELD nodeId, score
        WITH gds.util.asNode(nodeId) AS n, score
        SET n.pagerank = score
        RETURN count(n) AS written
        """)
    except Exception as e:
        print("PageRank stream failed:", e)
        try:
            gds.run_cypher(f"CALL gds.graph.drop('{GRAPH_NAME}') YIELD graphName")
        except Exception:
            pass
        gds.close()
        return

    # 4) Lấy top 20 nodes theo pagerank (thay exists(...) bằng IS NOT NULL)
    top_q = """
    MATCH (n)
    WHERE n.pagerank IS NOT NULL
    RETURN labels(n) AS labels, n.qid AS qid, n.name AS name, n.pagerank AS pagerank
    ORDER BY n.pagerank DESC
    LIMIT 20
    """
    try:
        df_top = gds.run_cypher(top_q)
        top_list = df_top.to_dict(orient="records") if hasattr(df_top, "to_dict") else [dict(r) for r in df_top]
    except Exception:
        res = gds.run_cypher(top_q)
        top_list = res if isinstance(res, list) else (res.to_dict(orient="records") if hasattr(res, "to_dict") else list(res))

    # 5) Ghi kết quả
    with open(os.path.abspath(OUTPUT_FILE), "w", encoding="utf-8") as f:
        json.dump(top_list, f, ensure_ascii=False, indent=2)

    print(f"Đã ghi top {len(top_list)} PageRank nodes -> {OUTPUT_FILE}")

    gds.close()

if __name__ == "__main__":
    main()