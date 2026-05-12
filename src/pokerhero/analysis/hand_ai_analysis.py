import os
import sqlite3
from typing import Dict, Any
import google.generativeai as genai
from pokerhero.analysis.generate_hand_text import generate_hand_text



class HandAIAnalyzer:
    def __init__(self, hero_username: str):
        # Configurar la API de Gemini
        api_key = os.environ.get("GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise ValueError("No se encontró la clave API de Google Gemini en las variables de entorno")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('models/gemini-flash-latest')
        self.hero_username = hero_username

    def analyze_hand(self, conn: sqlite3.Connection, hand_id: int) -> Dict[str, Any]:
        """
        Analiza una mano de poker utilizando IA.

        Args:
            conn: Conexión a la base de datos SQLite
            hand_id: ID de la mano a analizar

        Returns:
            Diccionario con el análisis de la mano
        """
        # Generar el texto de la mano
        hand_text = generate_hand_text(conn, hand_id)

        # Crear el prompt para la IA
        prompt = f"""
        Analiza esta mano de poker en formato PokerStars. El jugador Hero es {self.hero_username}. Proporciona un análisis detallado que incluya:

        1. Evaluación general de la mano
        2. Análisis de las decisiones preflop:
           - ¿Fue correcto el rango de apertura?
           - ¿Hubo errores en los calls/raises?
        3. Análisis de las decisiones postflop:
           - Evaluación de cada calle (flop, turn, river)
           - ¿Se jugó correctamente el board?
           - ¿Hubo oportunidades de bluff o value bet perdidas?
        4. Errores clave cometidos por los jugadores
        5. Lecciones aprendidas de esta mano
        6. Recomendaciones para mejorar

        Formato de la mano:
        {hand_text}

        Proporciona el análisis en formato Markdown con secciones claras.
        """

        try:
            # Generar el análisis con Gemini
            response = self.model.generate_content(prompt)

            return {
                "hand_id": hand_id,
                "analysis": response.text,
                "model": "gemini-pro",
                "status": "success"
            }
        except Exception as e:
            return {
                "hand_id": hand_id,
                "error": str(e),
                "status": "error"
            }

# Función de conveniencia para usar directamente
def analyze_hand_with_ai(conn: sqlite3.Connection, hand_id: int, hero_username: str) -> Dict[str, Any]:
    """Función de conveniencia para analizar una mano con IA."""
    analyzer = HandAIAnalyzer(hero_username=hero_username)
    return analyzer.analyze_hand(conn, hand_id)