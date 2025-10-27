Một vài lệnh thử nghiệm trên đồ thị dữ liệu

//Lệnh 1
MATCH (nolan:Person {name: "Christopher Nolan"})
      -[r1:DIRECTED|PRODUCED]->(f:Film)<-[r2:ACTED_IN]-(actor:Person)
RETURN nolan, r1, f, r2, actor
LIMIT 100


//lệnh 2
MATCH (p1:Person {name: "Angelina Jolie"})-[r1:ACTED_IN]->(f:Film)<-[r2:ACTED_IN]-(p2:Person)
MATCH (p2)-[r3:ACTED_IN]->(f2:Film)<-[r4:ACTED_IN]-(p3:Person)
WHERE p1 <> p2 AND p1 <> p3 AND p2 <> p3
RETURN p1, r1, f, r2, p2, r3, f2, r4, p3
LIMIT 50


//lệnh 3
MATCH path = (p1:Person {name: "Angelina Jolie"})-[:ACTED_IN*2]-(p3:Person)
WHERE p1 <> p3
RETURN path
LIMIT 50

//lệnh 4
MATCH (n) - [r] - (m)
RETURN n, r, m
LIMIT 200