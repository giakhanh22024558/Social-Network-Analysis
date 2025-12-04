import os
import json
import random
from neo4j import GraphDatabase
import networkx as nx
import numpy as np

# Cấu hình Neo4j (từ env hoặc mặc định)
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456aA@")

# Thông số cho baseline random graph
RANDOM_TRIALS = 5
# ngưỡng số node LCC để dùng exact APSP; nếu lớn hơn, dùng sampling
EXACT_APSP_THRESHOLD = 2000
SAMPLE_APSP_SOURCES = 200

def fetch_edges(driver):
    # Sử dụng elementId và không phụ thuộc vào property "title"
    q = """
    MATCH (a)-[r]->(b)
    RETURN elementId(a) AS a_eid, labels(a) AS a_labels,
           coalesce(a.name, a.qid, toString(elementId(a))) AS a_name,
           elementId(b) AS b_eid, labels(b) AS b_labels,
           coalesce(b.name, b.qid, toString(elementId(b))) AS b_name
    """
    rows = []
    with driver.session() as session:
        res = session.run(q)
        for r in res:
            rows.append(dict(r))
    return rows

def build_graph(rows):
    G = nx.Graph()
    for r in rows:
        a = r["a_eid"]; b = r["b_eid"]
        aname = r["a_name"]; bname = r["b_name"]
        G.add_node(a, label=','.join(r.get("a_labels") or []), name=aname)
        G.add_node(b, label=','.join(r.get("b_labels") or []), name=bname)
        if a != b:
            G.add_edge(a, b)
    return G

def exact_avg_shortest_path_length(G):
    return nx.average_shortest_path_length(G)

def approx_avg_shortest_path_length(G, samples=SAMPLE_APSP_SOURCES):
    # sampling single-source shortest-paths and average
    nodes = list(G.nodes())
    n = len(nodes)
    if n <= 1:
        return None
    k = min(samples, n)
    sources = random.sample(nodes, k)
    lengths = []
    for s in sources:
        dist = nx.single_source_shortest_path_length(G, s)
        # consider distances only to nodes in same component
        vals = list(dist.values())
        if len(vals) > 1:
            # exclude zero distance to self when averaging per-source
            lengths.append(np.mean([d for d in vals if d > 0]))
    if not lengths:
        return None
    return float(np.mean(lengths))

def avg_shortest_path_over_lcc(G):
    if G.number_of_nodes() == 0:
        return None
    # lấy largest connected component
    comps = list(nx.connected_components(G))
    lcc = max(comps, key=len)
    G_lcc = G.subgraph(lcc).copy()
    n = G_lcc.number_of_nodes()
    if n <= 1:
        return {"n": n, "avg_shortest_path": None, "avg_clustering": nx.average_clustering(G_lcc), "G_lcc": G_lcc}
    # chọn exact hay approx
    if n <= EXACT_APSP_THRESHOLD:
        avg_sp = exact_avg_shortest_path_length(G_lcc)
    else:
        avg_sp = approx_avg_shortest_path_length(G_lcc, samples=SAMPLE_APSP_SOURCES)
    avg_clust = nx.average_clustering(G_lcc)
    return {"n": n, "avg_shortest_path": avg_sp, "avg_clustering": avg_clust, "G_lcc": G_lcc}

def random_baseline_metrics(G_lcc, trials=RANDOM_TRIALS):
    n = G_lcc.number_of_nodes()
    m = G_lcc.number_of_edges()
    if n <= 1:
        return None

    sp_list = []
    clust_list = []

    for _ in range(trials):
        # dùng G(n, m)
        R = nx.gnm_random_graph(n, m)
        comps = list(nx.connected_components(R))
        R_lcc = R.subgraph(max(comps, key=len)).copy()

        # ASPL baseline
        if R_lcc.number_of_nodes() <= EXACT_APSP_THRESHOLD:
            sp = nx.average_shortest_path_length(R_lcc)
        else:
            sp = approx_avg_shortest_path_length(R_lcc, samples=SAMPLE_APSP_SOURCES)

        # clustering baseline trên LCC
        cl = nx.average_clustering(R_lcc)

        sp_list.append(sp)
        clust_list.append(cl)

    return {
        "avg_sp_rand": float(np.mean(sp_list)),
        "avg_clust_rand": float(np.mean(clust_list)),
    }

def compute_small_world_stats(G):
    res = avg_shortest_path_over_lcc(G)
    if res is None:
        raise RuntimeError("Graph empty")
    n = G.number_of_nodes()
    m = G.number_of_edges()
    lcc_n = res.get("n", 0)
    avg_sp = res.get("avg_shortest_path")
    avg_clust = res.get("avg_clustering")
    if avg_sp is None:
        return {"error": "LCC too small to compute shortest path."}
    baseline = random_baseline_metrics(res["G_lcc"], trials=RANDOM_TRIALS)
    if baseline is None:
        return {
            "n": n, "m": m, "lcc_n": lcc_n,
            "avg_shortest_path": avg_sp, "avg_clustering": avg_clust,
            "baseline": None,
            "note": "Không thể tính baseline ngẫu nhiên (quá nhỏ hoặc lỗi)."
        }
    # small-world sigma = (C / C_rand) / (L / L_rand)
    sigma = (avg_clust / baseline["avg_clust_rand"]) / (avg_sp / baseline["avg_sp_rand"])
    return {
        "n": n,
        "m": m,
        "lcc_n": lcc_n,
        "avg_shortest_path": avg_sp,
        "avg_clustering": avg_clust,
        "baseline_avg_shortest_path": baseline["avg_sp_rand"],
        "baseline_avg_clustering": baseline["avg_clust_rand"],
        "small_world_sigma": sigma
    }

def main(output_path="small_world_result.json"):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        rows = fetch_edges(driver)
        G = build_graph(rows)
        stats = compute_small_world_stats(G)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print("Kết quả:", stats)
    finally:
        driver.close()

if __name__ == "__main__":
    main()