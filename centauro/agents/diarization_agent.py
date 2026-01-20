"""
Agente de Diarización Mejorado v2.3

CAMBIOS EN v2.3:
- FIX CRÍTICO: Para Word pre-diarizado, SIEMPRE usa análisis de contenido primero
- El nombre del archivo ya NO influye en la detección del asesor
- Solo usa coincidencia de nombre como ÚLTIMO recurso (después de contenido)

CAMBIOS EN v2.2:
- FIX: Ya no asume que "el primero que habla es el ASESOR"
- NUEVO: Analiza el CONTENIDO para detectar quién es el asesor (anclas semánticas)

SOPORTA:
- VTT con speakers: <v NOMBRE>texto</v>
- VTT sin speakers: Usa UUID como identificador
- Word pre-diarizado: [NOMBRE]: texto (de Teams)
- Texto plano: Usa LLM + heurística
"""
import re
import json
from typing import List, Tuple, Optional, Dict
from ..llm_client import consultar_gpt


class DiarizationAgent:
    """Agente especializado en separar interlocutores en transcripciones"""
    
    def __init__(self, nombre_asesor: str = ""):
        """
        Args:
            nombre_asesor: Nombre del asesor (opcional, ya no es crítico en v2.3)
                          Se usa solo como hint secundario, NO como fuente principal
        """
        self.nombre_asesor = nombre_asesor
        self.ventana_contexto = 3
        self.confidence_threshold = 0.7
        self.asesor_detectado: Optional[str] = None
        
        # Anclas semánticas que identifican al ASESOR de OBS
        # Estas son palabras/frases que SOLO diría un asesor de ventas de OBS
        self.anclas_asesor = [
            # Institucionales (peso alto)
            r'universidad de barcelona',
            r'\bobs\b',
            r'obs business school',
            r'comité de admisiones',
            r'comité de admisión',
            
            # Proceso de venta (peso alto)
            r'sentido de esta reunión',
            r'grabar esta conversación',
            r'validar.*perfil',
            r'documentación necesaria',
            r'proceso de admisión',
            r'requisitos de admisión',
            
            # Producto (peso medio)
            r'matrícula',
            r'programa de (máster|master|mba)',
            r'metodología (de estudio|online)',
            r'campus virtual',
            r'convocatoria',
            r'claustro de profesores',
            r'plan de estudios',
            
            # Financiero (peso medio)
            r'beca',
            r'precio del programa',
            r'financiación',
            r'financiamiento',
            r'descuento',
            r'inversión del programa',
            
            # Frases típicas de asesor
            r'te voy a (explicar|contar|mostrar)',
            r'déjame (explicarte|contarte|mostrarte)',
            r'lo que te puedo (ofrecer|comentar)',
            r'alguna (duda|pregunta|consulta)',
            r'¿(te parece|qué te parece|cómo lo ves)\?',
        ]
        
        # Anclas que identifican al LEAD (cliente potencial)
        self.anclas_lead = [
            r'mi (trabajo|empresa|jefe|situación laboral)',
            r'trabajo en',
            r'llevo \d+ años',
            r'mi experiencia',
            r'¿cuánto cuesta',
            r'¿cuál es el precio',
            r'tengo que (pensarlo|consultarlo|hablarlo)',
            r'no estoy seguro',
            r'mi presupuesto',
        ]
        
    def diarizar(self, texto_crudo: str, log_id: str = "unknown") -> str:
        """Proceso completo de diarización con detección automática de formato"""
        print(f"🎙️ [DiarizationAgent v2.3] Iniciando...")
        self.asesor_detectado = None
        
        # DETECTAR FORMATO Y PROCESAR
        
        # 1. Word pre-diarizado ([NOMBRE]: texto)
        if self._es_word_prediarizado(texto_crudo):
            print("   🎯 Word pre-diarizado detectado ([NOMBRE]:)")
            return self._mapear_word_prediarizado(texto_crudo)
        
        # 2. Formato Teams/Word con "Nombre   HH:MM   texto"
        if self._es_formato_teams_con_timestamp(texto_crudo):
            print("   🎯 Formato Teams con timestamp detectado (Nombre HH:MM texto)")
            return self._mapear_formato_teams(texto_crudo)
        
        # 3. VTT con speakers (<v NOMBRE>)
        if self._es_vtt_con_speakers(texto_crudo):
            print("   🎯 VTT con speakers detectado (<v NOMBRE>)")
            return self._extraer_vtt_con_speakers(texto_crudo)
        
        # 4. VTT con UUID
        elif self._es_vtt_con_uuid(texto_crudo):
            print("   🎯 VTT con UUID detectado (speaker por ID)")
            return self._extraer_vtt_con_uuid(texto_crudo)
        
        # 5. Texto plano - usar clasificación contextual con LLM
        print(f"   📝 Texto sin formato específico, usando clasificación contextual")
        return self._diarizar_texto_plano(texto_crudo, log_id)
    
    # ==========================================================================
    # MAPEO INTELIGENTE DE NOMBRES A ROLES (CLAVE v2.3)
    # ==========================================================================
    
    def _mapear_nombres_a_roles(self, nombres: List[str], texto_completo: str = "") -> Dict[str, str]:
        """
        Mapea nombres reales a ASESOR/LEAD.
        
        ESTRATEGIA v2.3 (CONTENIDO PRIMERO):
        1. SIEMPRE analizar CONTENIDO primero para detectar quién habla como asesor
        2. Si el contenido no es concluyente, usar coincidencia de nombre como respaldo
        3. Fallback: el que tenga más "anclas de asesor" aunque sean pocas
        
        IMPORTANTE: El nombre del archivo (self.nombre_asesor) ya NO tiene prioridad
        """
        if len(nombres) == 1:
            self.asesor_detectado = nombres[0]
            return {nombres[0]: "ASESOR"}
        
        mapa = {}
        
        # === PASO 1: SIEMPRE analizar CONTENIDO primero ===
        if texto_completo:
            print("   🔍 Analizando contenido para identificar al asesor...")
            scores_asesor = self._calcular_score_asesor_por_contenido(nombres, texto_completo)
            scores_lead = self._calcular_score_lead_por_contenido(nombres, texto_completo)
            
            # Mostrar scores para debug
            for nombre in nombres:
                score_a = scores_asesor.get(nombre, 0)
                score_l = scores_lead.get(nombre, 0)
                print(f"      - {nombre}: {score_a} anclas ASESOR, {score_l} anclas LEAD")
            
            # Calcular score neto (asesor - lead)
            scores_netos = {
                nombre: scores_asesor.get(nombre, 0) - scores_lead.get(nombre, 0)
                for nombre in nombres
            }
            
            # El que tenga mayor score NETO es el ASESOR
            max_score = max(scores_netos.values())
            min_score = min(scores_netos.values())
            
            # Solo asignar si hay diferencia clara (al menos 2 puntos de diferencia)
            if max_score - min_score >= 2:
                asesor_detectado = max(scores_netos, key=scores_netos.get)
                mapa[asesor_detectado] = "ASESOR"
                print(f"   ✅ '{asesor_detectado}' identificado como ASESOR por contenido (score neto: {scores_netos[asesor_detectado]})")
            elif max_score > 0:
                # Si no hay diferencia clara pero alguien tiene score positivo
                asesor_detectado = max(scores_netos, key=scores_netos.get)
                mapa[asesor_detectado] = "ASESOR"
                print(f"   ⚠️ '{asesor_detectado}' identificado como ASESOR (score bajo, sin diferencia clara)")
        
        # === PASO 2: Si el contenido no fue concluyente, usar nombre como RESPALDO ===
        if "ASESOR" not in mapa.values() and self.nombre_asesor:
            print(f"   🔍 Contenido no concluyente, buscando coincidencia con nombre '{self.nombre_asesor}'...")
            for nombre in nombres:
                nombre_lower = nombre.lower()
                asesor_lower = self.nombre_asesor.lower()
                
                # Coincidencia flexible (parcial)
                if asesor_lower in nombre_lower or nombre_lower in asesor_lower:
                    mapa[nombre] = "ASESOR"
                    print(f"   ✅ '{nombre}' identificado como ASESOR (coincide con nombre configurado)")
                    break
                
                # Verificar por palabras individuales del nombre (>4 chars para evitar falsos positivos)
                palabras_asesor = [p for p in asesor_lower.split() if len(p) > 4]
                palabras_nombre = [p for p in nombre_lower.split() if len(p) > 4]
                
                for palabra in palabras_asesor:
                    if palabra in palabras_nombre:
                        mapa[nombre] = "ASESOR"
                        print(f"   ✅ '{nombre}' identificado como ASESOR (palabra '{palabra}' coincide)")
                        break
                
                if nombre in mapa:
                    break
        
        # === PASO 3: Fallback - el que tenga MÁS anclas de asesor (aunque sean pocas) ===
        if "ASESOR" not in mapa.values():
            if texto_completo:
                # Usar el que tenga más anclas de asesor
                scores_asesor = self._calcular_score_asesor_por_contenido(nombres, texto_completo)
                if any(s > 0 for s in scores_asesor.values()):
                    asesor_detectado = max(scores_asesor, key=scores_asesor.get)
                    mapa[asesor_detectado] = "ASESOR"
                    print(f"   ⚠️ Fallback por anclas: '{asesor_detectado}' como ASESOR (score: {scores_asesor[asesor_detectado]})")
                else:
                    # Último recurso: el primero
                    mapa[nombres[0]] = "ASESOR"
                    print(f"   ⚠️ Fallback final: '{nombres[0]}' como ASESOR (sin evidencia)")
            else:
                mapa[nombres[0]] = "ASESOR"
                print(f"   ⚠️ Fallback: '{nombres[0]}' como ASESOR (sin texto para analizar)")
        
        # Los demás son LEAD
        for nombre in nombres:
            if nombre not in mapa:
                mapa[nombre] = "LEAD"

        if "ASESOR" in mapa.values():
            self.asesor_detectado = next(n for n, rol in mapa.items() if rol == "ASESOR")
        
        return mapa
    
    def _calcular_score_asesor_por_contenido(self, nombres: List[str], texto: str) -> Dict[str, int]:
        """
        Analiza el texto de cada speaker y calcula un 'score de asesor'.
        Busca ANCLAS SEMÁNTICAS que solo diría un asesor de OBS.
        """
        scores = {nombre: 0 for nombre in nombres}
        
        for nombre in nombres:
            texto_speaker = self._extraer_texto_de_speaker(nombre, texto)
            
            if not texto_speaker:
                continue
            
            texto_lower = texto_speaker.lower()
            for ancla in self.anclas_asesor:
                matches = re.findall(ancla, texto_lower)
                scores[nombre] += len(matches)
        
        return scores
    
    def _calcular_score_lead_por_contenido(self, nombres: List[str], texto: str) -> Dict[str, int]:
        """
        Analiza el texto de cada speaker y calcula un 'score de lead'.
        Busca ANCLAS SEMÁNTICAS que solo diría un cliente potencial.
        """
        scores = {nombre: 0 for nombre in nombres}
        
        for nombre in nombres:
            texto_speaker = self._extraer_texto_de_speaker(nombre, texto)
            
            if not texto_speaker:
                continue
            
            texto_lower = texto_speaker.lower()
            for ancla in self.anclas_lead:
                matches = re.findall(ancla, texto_lower)
                scores[nombre] += len(matches)
        
        return scores
    
    def _extraer_texto_de_speaker(self, nombre: str, texto: str) -> str:
        """
        Extrae todo el texto dicho por un speaker específico.
        Soporta múltiples formatos.
        """
        texto_encontrado = []
        
        # Patrón 1: [Nombre]: texto
        patron1 = rf'\[{re.escape(nombre)}\]:\s*([^\[]+)'
        matches1 = re.findall(patron1, texto, re.IGNORECASE | re.DOTALL)
        texto_encontrado.extend(matches1)
        
        # Patrón 2: Nombre   HH:MM   texto (hasta el siguiente nombre o fin)
        otros_nombres = [n for n in self._extraer_nombres_del_texto(texto) if n.lower() != nombre.lower()]
        if otros_nombres:
            siguiente_speaker = "|".join([re.escape(n) for n in otros_nombres])
            patron2 = rf'{re.escape(nombre)}\s+\d+:\d+(?::\d+)?\s+(.+?)(?={siguiente_speaker}|\Z)'
        else:
            patron2 = rf'{re.escape(nombre)}\s+\d+:\d+(?::\d+)?\s+(.+?)(?:\n|$)'
        
        matches2 = re.findall(patron2, texto, re.IGNORECASE | re.DOTALL)
        texto_encontrado.extend(matches2)
        
        return " ".join(texto_encontrado)
    
    def _extraer_nombres_del_texto(self, texto: str) -> List[str]:
        """Extrae nombres únicos del texto (para formato Teams)"""
        patron = r'^(.+?)\s+\d+:\d+'
        nombres = []
        for linea in texto.split('\n')[:50]:
            match = re.match(patron, linea.strip())
            if match:
                nombre = match.group(1).strip()
                if nombre and nombre not in nombres:
                    nombres.append(nombre)
        return nombres
    
    # ==========================================================================
    # FORMATO TEAMS CON TIMESTAMP (Nombre   HH:MM   texto)
    # ==========================================================================
    
    def _es_formato_teams_con_timestamp(self, texto: str) -> bool:
        """
        Detecta formato: "Nombre   0:04   Hola, ¿cómo estás?"
        Típico de transcripciones de Teams/Zoom exportadas a Word
        """
        patron = r'^(.+?)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s+.+'
        lineas = texto.strip().split('\n')
        
        matches = 0
        for linea in lineas[:20]:
            if re.match(patron, linea.strip()):
                matches += 1
        
        return matches >= 2
    
    def _mapear_formato_teams(self, texto: str) -> str:
        """
        Procesa formato Teams: "Nombre   0:04   texto del mensaje"
        """
        patron = r'^(.+?)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$'
        
        lineas = texto.strip().split('\n')
        turnos = []
        nombres_encontrados = []
        
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
                
            match = re.match(patron, linea)
            if match:
                nombre = match.group(1).strip()
                texto_turno = match.group(3).strip()
                
                if nombre and texto_turno:
                    turnos.append({
                        "nombre": nombre,
                        "texto": texto_turno
                    })
                    if nombre not in nombres_encontrados:
                        nombres_encontrados.append(nombre)
        
        if not turnos:
            print("   ⚠️ No se pudieron extraer turnos, fallback a texto plano")
            return self._diarizar_texto_plano(texto, "fallback_teams")
        
        print(f"   📋 Nombres detectados: {nombres_encontrados}")
        
        # Mapear nombres a roles CON ANÁLISIS DE CONTENIDO
        mapa_speakers = self._mapear_nombres_a_roles(nombres_encontrados, texto)
        print(f"   🔄 Mapeo: {mapa_speakers}")
        
        # Construir diálogo diarizado
        dialogo = []
        for turno in turnos:
            rol = mapa_speakers.get(turno["nombre"], "LEAD")
            dialogo.append(f"[{rol}]: {turno['texto']}")
        
        # Fusionar turnos consecutivos del mismo speaker
        dialogo_fusionado = self._fusionar_texto_consecutivo(dialogo)
        
        turnos_asesor = sum(1 for d in dialogo_fusionado if d.startswith('[ASESOR]'))
        turnos_lead = sum(1 for d in dialogo_fusionado if d.startswith('[LEAD]'))
        print(f"   ✅ Mapeo completado: ASESOR={turnos_asesor}, LEAD={turnos_lead}")
        
        return "\n\n".join(dialogo_fusionado)
    
    # ==========================================================================
    # WORD PRE-DIARIZADO ([NOMBRE]: texto)
    # ==========================================================================
    
    def _es_word_prediarizado(self, texto: str) -> bool:
        """
        Detecta si el texto ya viene diarizado del Word de Teams
        Formato: [NOMBRE]: texto
        """
        patron = r'\[([^\]]+)\]:\s*'
        matches = re.findall(patron, texto[:2000])
        return len(matches) >= 2
    
    def _mapear_word_prediarizado(self, texto: str) -> str:
        """Mapea nombres del Word a ASESOR/LEAD"""
        # Extraer todos los nombres únicos
        patron_nombre = r'\[([^\]]+)\]:'
        nombres = re.findall(patron_nombre, texto)
        nombres_unicos = self._unique_in_order(nombres)
        
        print(f"   📋 Nombres detectados: {nombres_unicos}")
        
        # Mapear nombres a roles CON ANÁLISIS DE CONTENIDO (v2.3: contenido primero)
        mapa_speakers = self._mapear_nombres_a_roles(nombres_unicos, texto)
        print(f"   🔄 Mapeo: {mapa_speakers}")
        
        # Reemplazar nombres por roles
        resultado = texto
        for nombre, rol in mapa_speakers.items():
            patron_reemplazo = r'\[' + re.escape(nombre) + r'\]:'
            resultado = re.sub(patron_reemplazo, f'[{rol}]:', resultado)
        
        # Contar turnos
        turnos_asesor = resultado.count('[ASESOR]:')
        turnos_lead = resultado.count('[LEAD]:')
        
        print(f"   ✅ Mapeo completado: ASESOR={turnos_asesor}, LEAD={turnos_lead}")
        
        return resultado
    
    # ==========================================================================
    # VTT CON SPEAKERS (<v NOMBRE>texto</v>)
    # ==========================================================================
    
    def _es_vtt_con_speakers(self, texto: str) -> bool:
        """Detecta VTT con speakers: <v NOMBRE>texto</v>"""
        patron = r'<v\s+[^>]+>.*?</v>'
        matches = re.findall(patron, texto[:2000], re.IGNORECASE)
        return len(matches) >= 2
    
    def _extraer_vtt_con_speakers(self, texto_vtt: str) -> str:
        """Extrae diálogo de VTT con speakers explícitos"""
        patron = r'<v\s+([^>]+)>(.*?)</v>'
        matches = re.findall(patron, texto_vtt, re.DOTALL)
        
        if not matches:
            print("   ⚠️ No se encontraron speakers, fallback a método contextual")
            return self._diarizar_texto_plano(self._limpiar_vtt_basico(texto_vtt), "fallback_vtt")
        
        nombres_unicos = self._unique_in_order([nombre.strip() for nombre, _ in matches])
        
        # Reconstruir texto para análisis de contenido
        texto_para_analisis = "\n".join([
            f"[{nombre.strip()}]: {texto.strip()}" 
            for nombre, texto in matches if texto.strip()
        ])
        
        mapa_speakers = self._mapear_nombres_a_roles(nombres_unicos, texto_para_analisis)
        
        dialogo = []
        for nombre, texto in matches:
            nombre_clean = nombre.strip()
            rol = mapa_speakers.get(nombre_clean, "LEAD")
            texto_clean = texto.strip()
            
            if texto_clean:
                dialogo.append(f"[{rol}]: {texto_clean}")
        
        dialogo_fusionado = self._fusionar_texto_consecutivo(dialogo)
        
        print(f"   ✅ Extraídos {len(dialogo_fusionado)} turnos con speakers")
        return "\n\n".join(dialogo_fusionado)
    
    # ==========================================================================
    # VTT CON UUID (sin speakers explícitos)
    # ==========================================================================
    
    def _es_vtt_con_uuid(self, texto: str) -> bool:
        """Detecta VTT con UUID (sin speakers explícitos)"""
        patron = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}-\d+$'
        lineas = texto.split('\n')[:50]
        matches = [l for l in lineas if re.match(patron, l.strip())]
        return len(matches) >= 3
    
    def _extraer_vtt_con_uuid(self, texto_vtt: str) -> str:
        """Extrae diálogo de VTT usando UUID como identificador de speaker"""
        lineas = texto_vtt.split('\n')
        
        patron_uuid = r'^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})-\d+$'
        
        bloques = []
        uuid_actual = None
        texto_buffer = []
        
        for linea in lineas:
            linea = linea.strip()
            
            match = re.match(patron_uuid, linea)
            if match:
                if uuid_actual and texto_buffer:
                    bloques.append({
                        "uuid": uuid_actual,
                        "texto": " ".join(texto_buffer)
                    })
                
                uuid_actual = match.group(1)
                texto_buffer = []
            
            elif re.match(r'\d{2}:\d{2}:\d{2}\.\d{3}', linea):
                continue
            
            elif linea in ['WEBVTT', ''] or linea.startswith('NOTE'):
                continue
            
            elif uuid_actual:
                texto_buffer.append(linea)
        
        if uuid_actual and texto_buffer:
            bloques.append({
                "uuid": uuid_actual,
                "texto": " ".join(texto_buffer)
            })
        
        if not bloques:
            print("   ⚠️ No se pudieron extraer bloques, fallback")
            return self._diarizar_texto_plano(self._limpiar_vtt_basico(texto_vtt), "fallback_uuid")
        
        uuids_unicos = self._unique_in_order([b["uuid"] for b in bloques])
        
        # Para UUID, construimos texto temporal para análisis
        texto_por_uuid = {}
        for bloque in bloques:
            uuid = bloque["uuid"]
            if uuid not in texto_por_uuid:
                texto_por_uuid[uuid] = []
            texto_por_uuid[uuid].append(bloque["texto"])
        
        # Calcular scores por contenido
        scores = {}
        for uuid, textos in texto_por_uuid.items():
            texto_completo = " ".join(textos).lower()
            score = 0
            for ancla in self.anclas_asesor:
                if re.search(ancla, texto_completo):
                    score += 1
            scores[uuid] = score
        
        # El UUID con mayor score es el ASESOR
        if scores:
            uuid_asesor = max(scores, key=scores.get)
            if scores[uuid_asesor] > 0:
                print(f"   🔍 UUID del ASESOR detectado por contenido (score: {scores[uuid_asesor]})")
            else:
                uuid_asesor = uuids_unicos[0]
                print(f"   ⚠️ Sin anclas detectadas, asumiendo primer UUID como ASESOR")
        else:
            uuid_asesor = uuids_unicos[0]
        
        mapa = {uuid_asesor: "ASESOR"}
        for uuid in uuids_unicos:
            if uuid not in mapa:
                mapa[uuid] = "LEAD"
        
        dialogo = []
        for bloque in bloques:
            rol = mapa.get(bloque["uuid"], "LEAD")
            if bloque["texto"]:
                dialogo.append(f"[{rol}]: {bloque['texto']}")
        
        dialogo_fusionado = self._fusionar_texto_consecutivo(dialogo)
        
        print(f"   ✅ Extraídos {len(dialogo_fusionado)} turnos (UUID mapping)")
        return "\n\n".join(dialogo_fusionado)
    
    # ==========================================================================
    # TEXTO PLANO (usa LLM + heurística)
    # ==========================================================================
    
    def _diarizar_texto_plano(self, texto_crudo: str, log_id: str) -> str:
        """Diariza texto plano usando clasificación contextual"""
        frases = self._segmentar_por_pausas_naturales(texto_crudo)
        print(f"   📝 Detectadas {len(frases)} unidades conversacionales")
        
        dialogo_etiquetado = []
        speaker_anterior = None
        
        for idx, frase in enumerate(frases):
            speaker, confianza = self._clasificar_con_contexto(frases, idx, speaker_anterior)
            
            if speaker_anterior and speaker != speaker_anterior and confianza < self.confidence_threshold:
                print(f"   🔄 Re-evaluando turno {idx} (confianza baja: {confianza:.2f})")
                original_ventana = self.ventana_contexto
                self.ventana_contexto = 5
                speaker, confianza = self._clasificar_con_contexto(frases, idx, speaker_anterior)
                self.ventana_contexto = original_ventana
            
            dialogo_etiquetado.append({
                "speaker": speaker,
                "text": frase,
                "confidence": confianza,
                "index": idx
            })
            
            speaker_anterior = speaker
        
        dialogo_fusionado = self._fusionar_turnos_consecutivos(dialogo_etiquetado)
        
        resultado = "\n\n".join([
            f"[{turno['speaker']}]: {turno['text']}"
            for turno in dialogo_fusionado
        ])
        
        print(f"   ✅ Diarización completada: {len(dialogo_fusionado)} turnos")
        print(f"   📊 Distribución: {self._calcular_distribucion(dialogo_fusionado)}")
        
        return resultado
    
    # ==========================================================================
    # UTILIDADES
    # ==========================================================================
    
    def _fusionar_texto_consecutivo(self, dialogo: List[str]) -> List[str]:
        """Fusiona líneas consecutivas del mismo speaker"""
        if not dialogo:
            return []
        
        fusionado = []
        buffer = dialogo[0]
        
        for i in range(1, len(dialogo)):
            speaker_actual = dialogo[i].split(']:')[0] + ']'
            speaker_buffer = buffer.split(']:')[0] + ']'
            
            if speaker_actual == speaker_buffer:
                texto_nuevo = dialogo[i].split(']: ', 1)[1] if ']: ' in dialogo[i] else ""
                texto_buffer = buffer.split(']: ', 1)[1] if ']: ' in buffer else ""
                buffer = f"{speaker_actual}: {texto_buffer} {texto_nuevo}"
            else:
                fusionado.append(buffer)
                buffer = dialogo[i]
        
        fusionado.append(buffer)
        return fusionado
    
    @staticmethod
    def _unique_in_order(valores: List[str]) -> List[str]:
        """Devuelve valores únicos preservando orden de aparición."""
        vistos = set()
        resultado = []
        for valor in valores:
            if valor in vistos:
                continue
            vistos.add(valor)
            resultado.append(valor)
        return resultado
    
    def _limpiar_vtt_basico(self, texto_vtt: str) -> str:
        """Limpia VTT dejando solo el texto"""
        texto = texto_vtt.replace("WEBVTT", "")
        texto = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}', '', texto)
        texto = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(-\d+)?', '', texto)
        texto = re.sub(r'<[^>]+>', '', texto)
        lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
        return " ".join(lineas)
    
    def _segmentar_por_pausas_naturales(self, texto: str) -> List[str]:
        """Divide el texto respetando pausas conversacionales naturales"""
        if texto.count('\n') > len(texto) / 200:
            return [linea.strip() for linea in texto.split('\n') if linea.strip()]
        
        patron = r'(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])'
        frases = re.split(patron, texto)
        
        return [frase.strip() for frase in frases if frase.strip() and len(frase) > 10]
    
    def _clasificar_con_contexto(self, frases: List[str], idx: int, 
                                 speaker_anterior: Optional[str]) -> Tuple[str, float]:
        """Clasifica una frase usando ventana de contexto deslizante"""
        inicio = max(0, idx - self.ventana_contexto)
        fin = min(len(frases), idx + 2)
        contexto_frases = frases[inicio:fin]
        
        contexto_con_marca = []
        for i, frase in enumerate(contexto_frases):
            offset = i + inicio
            if offset == idx:
                contexto_con_marca.append(f">>> {frase}")
            else:
                contexto_con_marca.append(frase)
        
        contexto_texto = "\n".join(contexto_con_marca)
        
        try:
            resultado = self._clasificar_llm(contexto_texto, speaker_anterior)
            return resultado["speaker"], resultado["confianza"]
        except Exception as e:
            speaker = self._clasificar_heuristico(frases[idx], speaker_anterior)
            return speaker, 0.5
    
    def _clasificar_llm(self, contexto: str, speaker_anterior: Optional[str]) -> dict:
        """Clasifica usando el LLM con prompt especializado"""
        prompt_sistema = f"""
Eres un experto en análisis de diálogos comerciales de OBS Business School.

CONTEXTO:
- ASESOR: Quien vende, explica programas, hace preguntas estructuradas, menciona OBS/Universidad de Barcelona
- LEAD (Cliente): Quien pregunta sobre sí mismo, expresa dudas personales, habla de su trabajo/situación

TAREA:
Identifica quién dice la frase marcada con >>> en el contexto siguiente.

{f"CONTEXTO PREVIO: El speaker anterior era {speaker_anterior}" if speaker_anterior else ""}

FORMATO JSON OBLIGATORIO:
{{
  "speaker": "ASESOR" o "LEAD",
  "confianza": 0.0 a 1.0,
  "razon": "Justificación breve"
}}
"""
        
        resp = consultar_gpt(prompt_sistema, contexto, f"diar_classify")
        data = json.loads(resp)
        
        if "speaker" not in data:
            raise ValueError("Respuesta sin campo 'speaker'")
        
        return {
            "speaker": data["speaker"].upper(),
            "confianza": float(data.get("confianza", 0.5)),
            "razon": data.get("razon", "")
        }
    
    def _clasificar_heuristico(self, frase: str, speaker_anterior: Optional[str]) -> str:
        """Clasificación de respaldo basada en keywords"""
        frase_lower = frase.lower()
        
        score_asesor = 0
        score_lead = 0
        
        for ancla in self.anclas_asesor:
            if re.search(ancla, frase_lower):
                score_asesor += 1
        
        for ancla in self.anclas_lead:
            if re.search(ancla, frase_lower):
                score_lead += 1
        
        if score_asesor > score_lead:
            return "ASESOR"
        elif score_lead > score_asesor:
            return "LEAD"
        else:
            return speaker_anterior if speaker_anterior else "LEAD"
    
    def _fusionar_turnos_consecutivos(self, dialogo_etiquetado: List[dict]) -> List[dict]:
        """Une intervenciones consecutivas del mismo speaker"""
        if not dialogo_etiquetado:
            return []
        
        fusionado = []
        buffer = {
            "speaker": dialogo_etiquetado[0]["speaker"],
            "text": dialogo_etiquetado[0]["text"],
            "confidence": dialogo_etiquetado[0]["confidence"]
        }
        
        for i in range(1, len(dialogo_etiquetado)):
            turno_actual = dialogo_etiquetado[i]
            
            if turno_actual["speaker"] == buffer["speaker"]:
                buffer["text"] += f" {turno_actual['text']}"
                buffer["confidence"] = (buffer["confidence"] + turno_actual["confidence"]) / 2
            else:
                fusionado.append(buffer)
                buffer = {
                    "speaker": turno_actual["speaker"],
                    "text": turno_actual["text"],
                    "confidence": turno_actual["confidence"]
                }
        
        fusionado.append(buffer)
        return fusionado
    
    def _calcular_distribucion(self, dialogo: List[dict]) -> str:
        """Calcula estadísticas de distribución ASESOR vs LEAD"""
        total = len(dialogo)
        asesor_count = sum(1 for t in dialogo if t["speaker"] == "ASESOR")
        lead_count = total - asesor_count
        
        asesor_pct = (asesor_count / total * 100) if total > 0 else 0
        lead_pct = (lead_count / total * 100) if total > 0 else 0
        
        return f"ASESOR: {asesor_count} ({asesor_pct:.1f}%) | LEAD: {lead_count} ({lead_pct:.1f}%)"
