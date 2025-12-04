import os
import json
from graphdatascience import GraphDataScience

# Cấu hình Neo4j (từ env hoặc mặc định)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456aA@")

GRAPH_NAME = "communityGraph"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "community_detection_result.json")

# Các loại quan hệ (từ KEY_MAP)
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
    parts = []
    for k, v in rel_map.items():
        orient = v.get("orientation", "UNDIRECTED")
        parts.append(f"{k}: {{orientation: '{orient}'}}")
    return "{" + ", ".join(parts) + "}"

def main():
    gds = GraphDataScience(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # 1) Drop projection cũ nếu tồn tại
    try:
        exists_df = gds.run_cypher(f"CALL gds.graph.exists('{GRAPH_NAME}') YIELD exists")
        if not exists_df.empty and exists_df.loc[0, "exists"]:
            gds.run_cypher(f"CALL gds.graph.drop('{GRAPH_NAME}') YIELD graphName")
    except Exception:
        pass

    # 2) Tạo projection
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
        print("Không thể project graph, thử cypher fallback:", e)
        gds.run_cypher(f"""
        CALL gds.graph.project.cypher(
          '{GRAPH_NAME}',
          'MATCH (n) RETURN elementId(n) AS id',
          'MATCH (a)-[r]->(b) RETURN elementId(a) AS source, elementId(b) AS target'
        )
        """)

    # 3) Chạy Louvain (community detection) và ghi vào property
    try:
        gds.run_cypher(f"""
        CALL gds.louvain.stream('{GRAPH_NAME}')
        YIELD nodeId, communityId
        WITH gds.util.asNode(nodeId) AS n, communityId
        SET n.communityId = communityId
        RETURN count(n) AS written
        """)
    except Exception as e:
        print("Louvain stream failed:", e)
        try:
            gds.run_cypher(f"CALL gds.graph.drop('{GRAPH_NAME}') YIELD graphName")
        except Exception:
            pass
        gds.close()
        return

    # 4) Thống kê community: số lượng, kích thước từng community
    stats_q = """
    MATCH (n)
    WHERE n.communityId IS NOT NULL
    WITH n.communityId AS community, count(n) AS size
    RETURN community, size
    ORDER BY size DESC
    """
    try:
        df_stats = gds.run_cypher(stats_q)
        stats_list = df_stats.to_dict(orient="records") if hasattr(df_stats, "to_dict") else [dict(r) for r in df_stats]
    except Exception:
        res = gds.run_cypher(stats_q)
        stats_list = res if isinstance(res, list) else (res.to_dict(orient="records") if hasattr(res, "to_dict") else list(res))

    # 5) Lấy mẫu các node trong top 5 communities lớn nhất (mỗi community lấy tối đa 10 node)
    sample_q = """
    MATCH (n)
    WHERE n.communityId IS NOT NULL
    WITH n.communityId AS community, collect({qid: n.qid, name: n.name, labels: labels(n)}) AS members
    ORDER BY size(members) DESC
    LIMIT 5
    RETURN community, size(members) AS size, members[0..10] AS sample_members
    """
    try:
        df_sample = gds.run_cypher(sample_q)
        sample_list = df_sample.to_dict(orient="records") if hasattr(df_sample, "to_dict") else [dict(r) for r in df_sample]
    except Exception:
        res = gds.run_cypher(sample_q)
        sample_list = res if isinstance(res, list) else (res.to_dict(orient="records") if hasattr(res, "to_dict") else list(res))

    # 6) Tính modularity (chất lượng phân cộng đồng)
    try:
        mod_q = f"""
        CALL gds.louvain.stats('{GRAPH_NAME}')
        YIELD modularity, modularities
        RETURN modularity, modularities
        """
        df_mod = gds.run_cypher(mod_q)
        if not df_mod.empty:
            modularity = df_mod.loc[0, "modularity"]
            modularities = df_mod.loc[0, "modularities"]
        else:
            modularity = None
            modularities = None
    except Exception as e:
        print("Không thể tính modularity:", e)
        modularity = None
        modularities = None

    # 7) Ghi kết quả
    result = {
        "total_communities": len(stats_list),
        "modularity": modularity,
        "modularities_per_level": modularities,
        "community_sizes": stats_list[:20],  # top 20 communities lớn nhất
        "top5_communities_sample": sample_list
    }

    with open(os.path.abspath(OUTPUT_FILE), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Đã ghi kết quả community detection -> {OUTPUT_FILE}")
    print(f"  - Tổng số communities: {result['total_communities']}")
    print(f"  - Modularity: {result['modularity']}")

    gds.close()

if __name__ == "__main__":
    main()