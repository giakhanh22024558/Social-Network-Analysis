# --- CÀI THƯ VIỆN ---
# pip install py2neo networkx matplotlib pandas

from py2neo import Graph
import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd

# --- KẾT NỐI NEO4J ---
graph = Graph("bolt://127.0.0.1:7687", auth=("neo4j", "123456aA@"))  # đổi mật khẩu cho phù hợp

# --- TRUY VẤN QUAN HỆ DIỄN VIÊN-HỢP TÁC ---
query = """
MATCH (a:Person)-[:ACTED_IN]->(f:Film)<-[:ACTED_IN]-(b:Person)
WHERE a <> b
RETURN a.name AS actor1, b.name AS actor2
LIMIT 1000
"""
records = graph.run(query).data()

# --- TẠO ĐỒ THỊ NETWORKX ---
G = nx.Graph()
for r in records:
    G.add_edge(r["actor1"], r["actor2"])

print(f"Số nút: {G.number_of_nodes()}, Số cạnh: {G.number_of_edges()}")

# --- TÍNH TOÁN CÁC CHỈ SỐ TRUNG TÂM ---
degree_centrality = nx.degree_centrality(G)
betweenness_centrality = nx.betweenness_centrality(G, normalized=True)
pagerank_centrality = nx.pagerank(G, alpha=0.85)

# --- CHUYỂN DỮ LIỆU THÀNH BẢNG ---
df = pd.DataFrame({
    'Actor': list(degree_centrality.keys()),
    'Degree': list(degree_centrality.values()),
    'Betweenness': [betweenness_centrality.get(a, 0) for a in degree_centrality.keys()],
    'PageRank': [pagerank_centrality.get(a, 0) for a in degree_centrality.keys()]
})

# --- LẤY TOP 10 THEO PAGE RANK (hoặc Degree) ---
top_10 = df.sort_values(by="PageRank", ascending=False).head(10)
print(top_10)

# --- VẼ BIỂU ĐỒ SO SÁNH ---
plt.figure(figsize=(10, 6))
x = range(len(top_10))

plt.plot(x, top_10["Degree"], marker='o', label='Degree Centrality')
plt.plot(x, top_10["Betweenness"], marker='s', label='Betweenness Centrality')
plt.plot(x, top_10["PageRank"], marker='^', label='PageRank')

plt.xticks(x, top_10["Actor"], rotation=45, ha='right')
plt.title("So sánh các chỉ số trung tâm của Top 10 diễn viên")
plt.xlabel("Tên diễn viên")
plt.ylabel("Giá trị chuẩn hoá")
plt.legend()
plt.tight_layout()
plt.show()

# --- LƯU KẾT QUẢ (nếu muốn) ---
top_10.to_csv("centrality_top10.csv", index=False)
