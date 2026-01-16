"""
Agente de Diarización Mejorado v2.1

INSTRUCCIÓN: REEMPLAZA el contenido de:
C:\\Users\\uscp9a\\Grupo Planeta\\BI POWER - General\\PBI\\PROYECTOS\\Proyecto_Centauro\\centauro\\agents\\diarization_agent.py

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
    
    def __init__(self, nombre_asesor: str):
        self.nombre_asesor = nombre_asesor
        self.ventana_contexto = 3
        self.confidence_threshold = 0.7
        
    def diarizar(self, texto_crudo: str, log_id: str = "unknown") -> str:
        """Proceso completo de diarización con detección automática de formato"""
        print(f"🎙️ [DiarizationAgent v2.1] Iniciando para: {self.nombre_asesor}")
        
        # NUEVO: Detectar si YA está diarizado (Word de Teams)
        if self._es_word_prediarizado(texto_crudo):
            print("   🎯 Word pre-diarizado detectado ([NOMBRE]:)")
            return self._mapear_word_prediarizado(texto_crudo)
        
        # Detectar formato VTT con speakers
        if self._es_vtt_con_speakers(texto_crudo):
            print("   🎯 VTT con speakers detectado (<v NOMBRE>)")
            return self._extraer_vtt_con_speakers(texto_crudo)
        
        # Detectar VTT con UUID
        elif self._es_vtt_con_uuid(texto_crudo):
            print("   🎯 VTT con UUID detectado (speaker por ID)")
            return self._extraer_vtt_con_uuid(texto_crudo)
        
        # Si no es ninguno de los anteriores, usar método contextual
        print(f"   📝 Texto sin formato específico, usando clasificación contextual")
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
    
    # ========== NUEVO: SOPORTE PARA WORD PRE-DIARIZADO ==========
    
    def _es_word_prediarizado(self, texto: str) -> bool:
        """
        Detecta si el texto ya viene diarizado del Word de Teams
        Formato: [NOMBRE]: texto
        """
        patron = r'\[([^\]]+)\]:\s*'
        matches = re.findall(patron, texto[:2000])
        return len(matches) >= 2  # Al menos 2 turnos detectados
    
    def _mapear_word_prediarizado(self, texto: str) -> str:
        """
        Mapea nombres del Word a ASESOR/LEAD
        """
        # Extraer todos los nombres únicos
        patron_nombre = r'\[([^\]]+)\]:'
        nombres = re.findall(patron_nombre, texto)
        nombres_unicos = self._unique_in_order(nombres)
        
        print(f"   📋 Nombres detectados: {nombres_unicos}")
        
        # Mapear nombres a roles
        mapa_speakers = self._mapear_nombres_a_roles(nombres_unicos)
        
        print(f"   🔄 Mapeo: {mapa_speakers}")
        
        # Reemplazar nombres por roles
        resultado = texto
        for nombre, rol in mapa_speakers.items():
            # Reemplazar [NOMBRE]: por [ROL]:
            patron_reemplazo = r'\[' + re.escape(nombre) + r'\]:'
            resultado = re.sub(patron_reemplazo, f'[{rol}]:', resultado)
        
        # Contar turnos
        turnos_asesor = resultado.count('[ASESOR]:')
        turnos_lead = resultado.count('[LEAD]:')
        
        print(f"   ✅ Mapeo completado: ASESOR={turnos_asesor}, LEAD={turnos_lead}")
        
        return resultado
    
    # ========== DETECTORES DE FORMATO VTT ==========
    
    def _es_vtt_con_speakers(self, texto: str) -> bool:
        """Detecta VTT con speakers: <v NOMBRE>texto</v>"""
        patron = r'<v\s+[^>]+>.*?</v>'
        matches = re.findall(patron, texto[:2000], re.IGNORECASE)
        return len(matches) >= 2
    
    def _es_vtt_con_uuid(self, texto: str) -> bool:
        """Detecta VTT con UUID (sin speakers explícitos)"""
        patron = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}-\d+$'
        lineas = texto.split('\n')[:50]
        matches = [l for l in lineas if re.match(patron, l.strip())]
        return len(matches) >= 3
    
    def _extraer_vtt_con_speakers(self, texto_vtt: str) -> str:
        """Extrae diálogo de VTT con speakers explícitos"""
        patron = r'<v\s+([^>]+)>(.*?)</v>'
        matches = re.findall(patron, texto_vtt, re.DOTALL)
        
        if not matches:
            print("   ⚠️ No se encontraron speakers, fallback a método contextual")
            return self.diarizar(self._limpiar_vtt_basico(texto_vtt), "fallback")
        
        nombres_unicos = self._unique_in_order([nombre.strip() for nombre, _ in matches])
        mapa_speakers = self._mapear_nombres_a_roles(nombres_unicos)
        
        dialogo = []
        for nombre, texto in matches:
            nombre_clean = nombre.strip()
            rol = mapa_speakers.get(nombre_clean, "LEAD")
            texto_clean = texto.strip()
            
            if texto_clean:
                dialogo.append(f"[{rol}]: {texto_clean}")
        
        # Fusionar turnos consecutivos
        dialogo_fusionado = self._fusionar_texto_consecutivo(dialogo)
        
        print(f"   ✅ Extraídos {len(dialogo_fusionado)} turnos con speakers")
        return "\n\n".join(dialogo_fusionado)
    
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
            return self.diarizar(self._limpiar_vtt_basico(texto_vtt), "fallback")
        
        uuids_unicos = self._unique_in_order([b["uuid"] for b in bloques])
        
        if len(uuids_unicos) == 1:
            mapa = {uuids_unicos[0]: "ASESOR"}
        elif len(uuids_unicos) == 2:
            primer_uuid = bloques[0]["uuid"]
            segundo_uuid = [u for u in uuids_unicos if u != primer_uuid][0]
            mapa = {
                primer_uuid: "ASESOR",
                segundo_uuid: "LEAD"
            }
        else:
            mapa = {uuids_unicos[0]: "ASESOR"}
            for uuid in uuids_unicos[1:]:
                mapa[uuid] = "LEAD"
        
        dialogo = []
        for bloque in bloques:
            rol = mapa.get(bloque["uuid"], "LEAD")
            if bloque["texto"]:
                dialogo.append(f"[{rol}]: {bloque['texto']}")
        
        dialogo_fusionado = self._fusionar_texto_consecutivo(dialogo)
        
        print(f"   ✅ Extraídos {len(dialogo_fusionado)} turnos (UUID mapping)")
        return "\n\n".join(dialogo_fusionado)
    
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
                texto_nuevo = dialogo[i].split(']: ', 1)[1]
                texto_buffer = buffer.split(']: ', 1)[1]
                buffer = f"{speaker_actual}: {texto_buffer} {texto_nuevo}"
            else:
                fusionado.append(buffer)
                buffer = dialogo[i]
        
        fusionado.append(buffer)
        return fusionado
    
    def _mapear_nombres_a_roles(self, nombres: List[str]) -> Dict[str, str]:
        """Mapea nombres reales a ASESOR/LEAD"""
        if len(nombres) == 1:
            return {nombres[0]: "ASESOR"}
        
        mapa = {}
        
        for nombre in nombres:
            # Si el nombre coincide con el asesor configurado
            if self.nombre_asesor.lower() in nombre.lower() or nombre.lower() in self.nombre_asesor.lower():
                mapa[nombre] = "ASESOR"
            else:
                mapa[nombre] = "LEAD"
        
        # Si no mapeamos ninguno como ASESOR, el primero es ASESOR
        if "ASESOR" not in mapa.values():
            mapa[nombres[0]] = "ASESOR"
            for n in nombres[1:]:
                if n not in mapa:
                    mapa[n] = "LEAD"
        
        return mapa

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
    
    # ========== MÉTODOS EXISTENTES ==========
    
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
Eres un experto en análisis de diálogos comerciales.

CONTEXTO:
- ASESOR ({self.nombre_asesor}): Quien vende, explica programas, hace preguntas estructuradas
- LEAD (Cliente): Quien pregunta sobre sí mismo, expresa dudas personales

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
        
        patrones_asesor_fuertes = [
            r'\b(obs business school|universidad de barcelona)\b',
            r'\b(matrícula|admisión|documentación necesaria)\b',
            r'\b(alguna duda|te parece bien|perfecto entonces)\b',
            r'\b(cuéntame|explícame más|qué te motivó)\b'
        ]
        
        patrones_lead_fuertes = [
            r'\b(mi trabajo|mi jefe|mi empresa|mi situación)\b',
            r'\b(trabajo en|llevo \d+ años|soy de)\b',
            r'\b(cuánto cuesta|precio total|qué incluye)\b'
        ]
        
        score_asesor = 0
        score_lead = 0
        
        for patron in patrones_asesor_fuertes:
            if re.search(patron, frase_lower):
                score_asesor += 3
        
        for patron in patrones_lead_fuertes:
            if re.search(patron, frase_lower):
                score_lead += 3
        
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
