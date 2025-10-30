from py2neo import Graph
import pandas as pd
import matplotlib.pyplot as plt
import os
import sys
import logging
import textwrap
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Configuration (can be overridden via environment variables)
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASS", "123456aA@")
OUT_DIR = Path("figures")
TOP_N = 10

def safe_run_query(graph, query, expected_cols):
    try:
        df = graph.run(query).to_data_frame()
    except Exception as e:
        logging.error("Query failed: %s", e)
        return pd.DataFrame(columns=expected_cols)
    # Ensure expected columns exist
    for col in expected_cols:
        if col not in df.columns:
            df[col] = []
    return df

def shorten_labels(values, width=40):
    return [textwrap.shorten(str(v), width=width, placeholder="...") for v in values]

def run_analysis():
    # Connect to Neo4j
    try:
        graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        # quick connectivity check
        graph.run("RETURN 1").data()
    except Exception as e:
        logging.error("Unable to connect to Neo4j at %s: %s", NEO4J_URI, e)
        sys.exit(1)

    # --- Ensure director name fix: Q3772 -> Quentin_Tarantino ---
    try:
        update_query = """
        MATCH (d:Person {name: $old})
        SET d.name = $new
        RETURN count(d) AS updated
        """
        res = graph.run(update_query, old="Q3772", new="Quentin_Tarantino").data()
        updated = res[0]["updated"] if res else 0
        if updated:
            logging.info("Renamed %d node(s) from 'Q3772' to 'Quentin_Tarantino'.", updated)
        else:
            logging.info("No nodes named 'Q3772' found; no rename necessary.")
    except Exception as e:
        logging.error("Failed to rename director 'Q3772': %s", e)

    # Ensure output directory exists
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Phần 1: Phim có nhiều diễn viên nhất ---
    query_films = f"""
    MATCH (f:Film)<-[:ACTED_IN]-(p:Person)
    WITH f, COUNT(p) AS actor_count
    RETURN CASE
      WHEN f.name IS NULL OR trim(f.name) = '' THEN '<no name_' + toString(id(f)) + '>'
      ELSE f.name
    END AS film, actor_count
    ORDER BY actor_count DESC
    LIMIT {TOP_N}
    """
    films = safe_run_query(graph, query_films, expected_cols=["film", "actor_count"])

    # --- Phần 2: Đạo diễn có mạng lưới hợp tác rộng nhất ---
    query_directors = f"""
    MATCH (d:Person)-[:DIRECTED]->(f:Film)<-[:ACTED_IN]-(a:Person)
    RETURN d.name AS director, COUNT(DISTINCT a) AS collaborator_count
    ORDER BY collaborator_count DESC
    LIMIT {TOP_N}
    """
    directors = safe_run_query(graph, query_directors, expected_cols=["director", "collaborator_count"])

    if films.empty:
        logging.warning("No film results returned.")
    if directors.empty:
        logging.warning("No director results returned.")

    print("🎬 Top phim có nhiều diễn viên nhất:")
    print(films.to_string(index=False), "\n")

    print("🎥 Top đạo diễn có mạng lưới hợp tác rộng nhất:")
    print(directors.to_string(index=False), "\n")

    # --- Vẽ biểu đồ minh hoạ ---
    if films.empty and directors.empty:
        logging.info("No data to plot. Exiting.")
        return

    plt.figure(figsize=(12, 6))
    plot_count = 0

    if not films.empty:
        ax1 = plt.subplot(1, 2, 1)
        labels = shorten_labels(films["film"].astype(str).tolist(), width=35)
        counts = films["actor_count"].astype(int).tolist()
        ax1.barh(labels, counts, color="skyblue")
        ax1.set_title("Top phim có nhiều diễn viên tham gia")
        ax1.set_xlabel("Số lượng diễn viên")
        ax1.invert_yaxis()
        plot_count += 1
    else:
        # empty placeholder
        ax1 = plt.subplot(1, 2, 1)
        ax1.text(0.5, 0.5, "No film data", ha="center", va="center")
        ax1.axis("off")

    if not directors.empty:
        ax2 = plt.subplot(1, 2, 2)
        labels = shorten_labels(directors["director"].astype(str).tolist(), width=35)
        counts = directors["collaborator_count"].astype(int).tolist()
        ax2.barh(labels, counts, color="lightcoral")
        ax2.set_title("Top đạo diễn có mạng lưới hợp tác rộng")
        ax2.set_xlabel("Số lượng diễn viên hợp tác")
        ax2.invert_yaxis()
        plot_count += 1
    else:
        ax2 = plt.subplot(1, 2, 2)
        ax2.text(0.5, 0.5, "No director data", ha="center", va="center")
        ax2.axis("off")

    plt.tight_layout()
    out_path = OUT_DIR / "film_director_summary.png"
    plt.savefig(out_path, dpi=300)
    logging.info("Saved figure to %s", out_path)
    plt.show()

if __name__ == "__main__":
    run_analysis()
