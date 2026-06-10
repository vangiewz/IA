import os
import pandas as pd
import random
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import logging

logger = logging.getLogger(__name__)

class RoutingEngineService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RoutingEngineService, cls).__new__(cls)
            cls._instance.model_prioridad = None
            cls._instance.model_riesgo = None
            cls._instance.model_tiempo = None
            cls._instance.model_anomalia = None
            cls._instance.preprocessor = None
            cls._instance.is_trained = False
            cls._instance.csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "historico_tramites.csv")
        return cls._instance

    def initialize_and_train(self):
        if self.is_trained:
            return
        
        # Regenerar CSV si no tiene la nueva estructura
        try:
            df_check = pd.read_csv(self.csv_path)
            if 'tema_principal' not in df_check.columns:
                os.remove(self.csv_path)
                logger.info("Eliminado dataset antiguo, regenerando para arquitectura híbrida.")
        except Exception:
            pass

        if not os.path.exists(self.csv_path):
            logger.info("CSV no encontrado. Generando mock data híbrida...")
            self._generate_mock_data()
        
        logger.info("Entrenando modelo Random Forest...")
        self.train_model()
        logger.info("Modelo Híbrido entrenado con éxito.")

    def _generate_mock_data(self):
        data = []
        temas = ['Tecnico', 'Financiero', 'Legal', 'Administrativo', 'Atencion_Cliente']
        tonos = ['Calmado', 'Molesto', 'Emergencia', 'Neutro']
        departamentos = ['RRHH', 'Finanzas', 'Operaciones', 'IT', 'Legal', 'Ventas']
        
        for i in range(2000):
            tema = random.choice(temas)
            tono = random.choice(tonos)
            menciona_fecha = random.choice([True, False])
            depto = random.choice(departamentos)
            carga = random.randint(0, 50)
            es_fin = random.choice([True, False])
            
            puntos_criticidad = 0
            if tono == 'Emergencia': puntos_criticidad += 3
            if tono == 'Molesto': puntos_criticidad += 1
            if tema in ['Legal', 'Tecnico']: puntos_criticidad += 1
            if menciona_fecha: puntos_criticidad += 1
            if es_fin and tono == 'Emergencia': puntos_criticidad += 2
            
            if puntos_criticidad >= 4:
                prioridad = "ALTA"
            elif puntos_criticidad >= 2:
                prioridad = "MEDIA"
            else:
                prioridad = "BAJA"
                
            riesgo = False
            if prioridad == "ALTA" and carga > 20:
                riesgo = True
            elif tema == 'Legal' and menciona_fecha and carga > 10:
                riesgo = True
                
            tiempo_base = random.randint(1, 10)
            if riesgo: tiempo_base += 15
            if carga > 30: tiempo_base += 5
            tiempo_resolucion_dias = tiempo_base + random.random()
                
            data.append({
                "tema_principal": tema,
                "tono_cliente": tono,
                "menciona_fechas_limite": int(menciona_fecha),
                "departamento_asignado": depto,
                "carga_actual_departamento": carga,
                "es_viernes_o_fin_semana": int(es_fin),
                "prioridad": prioridad,
                "riesgo_demora": int(riesgo),
                "tiempo_resolucion_dias": round(tiempo_resolucion_dias, 2)
            })
            
        df = pd.DataFrame(data)
        df.to_csv(self.csv_path, index=False)
        logger.info(f"Mock data (Híbrida) generado en: {self.csv_path}")

    def train_model(self):
        df = pd.read_csv(self.csv_path)
        
        X = df[['tema_principal', 'tono_cliente', 'menciona_fechas_limite', 'departamento_asignado', 'carga_actual_departamento', 'es_viernes_o_fin_semana']]
        y_prioridad = df['prioridad']
        y_riesgo = df['riesgo_demora']
        y_tiempo = df['tiempo_resolucion_dias']
        
        categorical_features = ['tema_principal', 'tono_cliente', 'departamento_asignado']
        numerical_features = ['menciona_fechas_limite', 'carga_actual_departamento', 'es_viernes_o_fin_semana']
        
        self.preprocessor = ColumnTransformer(
            transformers=[
                ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features),
                ('num', 'passthrough', numerical_features)
            ]
        )
        
        self.model_prioridad = Pipeline([
            ('preprocessor', self.preprocessor),
            ('classifier', MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=500, random_state=42))
        ])
        
        self.model_riesgo = Pipeline([
            ('preprocessor', self.preprocessor),
            ('classifier', MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=500, random_state=42))
        ])
        
        self.model_tiempo = Pipeline([
            ('preprocessor', self.preprocessor),
            ('regressor', MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=500, random_state=42))
        ])
        
        self.model_anomalia = Pipeline([
            ('preprocessor', self.preprocessor),
            ('detector', IsolationForest(contamination=0.05, random_state=42))
        ])
        
        self.model_prioridad.fit(X, y_prioridad)
        self.model_riesgo.fit(X, y_riesgo)
        self.model_tiempo.fit(X, y_tiempo)
        self.model_anomalia.fit(X)
        self.is_trained = True

    def predict_hybrid(self, features: dict) -> dict:
        if not self.is_trained:
            logger.warning("El modelo no está entrenado. Retornando defaults.")
            return {"prioridad": "MEDIA", "riesgoDemora": False}
            
        X_new = pd.DataFrame([features])
        
        try:
            pred_prioridad = self.model_prioridad.predict(X_new)[0]
            pred_riesgo = self.model_riesgo.predict(X_new)[0]
            pred_tiempo = self.model_tiempo.predict(X_new)[0]
            pred_anomalia = self.model_anomalia.predict(X_new)[0]
            es_anomalo = bool(pred_anomalia == -1)
        except Exception as e:
            logger.error(f"Error prediciendo con Red Neuronal: {e}")
            pred_prioridad = "MEDIA"
            pred_riesgo = False
            pred_tiempo = 5.0
            es_anomalo = False
            
        return {
            "prioridad": str(pred_prioridad),
            "riesgoDemora": bool(pred_riesgo),
            "tiempoEstimadoDias": float(pred_tiempo),
            "esAnomalo": es_anomalo
        }

    def append_feedback_and_retrain(self, real_data: dict) -> bool:
        """
        Guarda un caso real en historico_tramites.csv y reentrena el modelo.
        real_data debe tener: tema_principal, tono_cliente, menciona_fechas_limite, 
        departamento_asignado, carga_actual_departamento, es_viernes_o_fin_semana,
        prioridad (real), riesgo_demora (real), tiempo_resolucion_dias (real)
        """
        if not os.path.exists(self.csv_path):
            self.initialize_and_train()
            
        try:
            # Crear DataFrame con 1 fila
            new_row = pd.DataFrame([real_data])
            
            # Asegurar orden de columnas
            expected_columns = [
                'tema_principal', 'tono_cliente', 'menciona_fechas_limite', 
                'departamento_asignado', 'carga_actual_departamento', 
                'es_viernes_o_fin_semana', 'prioridad', 'riesgo_demora', 
                'tiempo_resolucion_dias'
            ]
            new_row = new_row[expected_columns]
            
            # Append al CSV
            new_row.to_csv(self.csv_path, mode='a', header=False, index=False)
            logger.info("Nuevo caso real guardado en historico_tramites.csv")
            
            # Reentrenar modelo en caliente
            logger.info("Iniciando reentrenamiento en caliente por Feedback Continuo...")
            self.train_model()
            logger.info("Modelo reentrenado exitosamente con el nuevo caso.")
            return True
        except Exception as e:
            logger.error(f"Error procesando feedback: {e}")
            return False
