CREATE VIEW jugadores_stack_medio_view AS
SELECT 
  player_id,
  (SELECT 
     AVG(starting_stack) 
   FROM (
     SELECT 
       starting_stack
     FROM hand_players 
     WHERE player_id = player_id 
     ORDER BY starting_stack 
     LIMIT 1 OFFSET (SELECT 
                      COUNT(*) / 2 
                    FROM hand_players 
                    WHERE player_id = player_id)
   )) AS stack_medio
FROM (
  SELECT DISTINCT player_id 
  FROM hand_players
) AS jugadores;

CREATE VIEW jugadores_stats_view AS
SELECT 
  p.username AS nombre,
  COUNT(DISTINCT hp.hand_id) AS manos_jugadas,
  SUM(hp.net_result) AS ganancias_perdidas,
  MAX(h.timestamp) AS ultima_fecha,
  MIN(h.timestamp) AS primera_fecha,
  AVG(CASE WHEN hp.vpip = 1 THEN 1 ELSE 0 END) * 100 AS vpip,
  AVG(CASE WHEN hp.pfr = 1 THEN 1 ELSE 0 END) * 100 AS pfr,
  js.stack_medio,
  (strftime('%s', MAX(h.timestamp)) - strftime('%s', MIN(h.timestamp))) / 86400 AS dias_jugados
FROM players p
JOIN hand_players hp ON p.id = hp.player_id
JOIN hands h ON hp.hand_id = h.id
JOIN jugadores_stack_medio_view js ON p.id = js.player_id
GROUP BY p.id, p.username, js.stack_medio;
