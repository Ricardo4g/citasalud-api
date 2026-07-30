from pathlib import Path
from datetime import date, datetime, time, timedelta
from typing import List, Optional
import sqlite3
import requests
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import Column, Date, ForeignKey, Integer, String, Time, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------------
# Credenciales de WhatsApp Green API
# ---------------------
GREEN_API_URL = "https://7107.api.greenapi.com/waInstance710722697464/sendMessage/7ea70a0d63ac4cfc8f9ce9d9f81e76a12e0033f9534e48a680"
WEBHOOK_VERIFY_TOKEN = "citasalud_token_seguro_123"

# ---------------------
# Configuración de la base de datos
# ---------------------
DATABASE_URL = "sqlite:///citasalud.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------
# Modelos de SQLAlchemy
# ---------------------
class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    correo = Column(String, unique=True, index=True, nullable=False)
    contrasena_hash = Column(String, nullable=False)
    rol = Column(String, nullable=False)
    especialidad = Column(String, nullable=True, default="")
    telefono = Column(String, nullable=True)
    activo = Column(Integer, nullable=False, default=1)
    recuperacion_token = Column(String, nullable=True)
    citas_paciente = relationship("Cita", back_populates="paciente", foreign_keys="Cita.paciente_id")
    citas_medico = relationship("Cita", back_populates="medico", foreign_keys="Cita.medico_id")

class Cita(Base):
    __tablename__ = "citas"
    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    medico_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)
    motivo = Column(String, nullable=True)
    estado = Column(String, nullable=False, default="pendiente")
    paciente = relationship("Usuario", back_populates="citas_paciente", foreign_keys=[paciente_id])
    medico = relationship("Usuario", back_populates="citas_medico", foreign_keys=[medico_id])

SECRET_KEY = "citasalud-secret-key-123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
failed_login_attempts: dict[tuple[str, str], list[datetime]] = {}

def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def _cleanup_login_attempts():
    window_start = datetime.utcnow() - timedelta(minutes=LOGIN_WINDOW_MINUTES)
    for key, attempts in list(failed_login_attempts.items()):
        failed_login_attempts[key] = [t for t in attempts if t > window_start]
        if not failed_login_attempts[key]:
            del failed_login_attempts[key]

def _record_failed_login(email: str, ip: str) -> None:
    key = (email.lower().strip(), ip)
    _cleanup_login_attempts()
    attempts = failed_login_attempts.setdefault(key, [])
    attempts.append(datetime.utcnow())
    if len(attempts) > MAX_LOGIN_ATTEMPTS:
        failed_login_attempts[key] = attempts[-MAX_LOGIN_ATTEMPTS:]

def _is_login_blocked(email: str, ip: str) -> bool:
    key = (email.lower().strip(), ip)
    _cleanup_login_attempts()
    return len(failed_login_attempts.get(key, [])) >= MAX_LOGIN_ATTEMPTS

def migrate_database():
    with sqlite3.connect("citasalud.db") as conn:
        cursor = conn.cursor()
        for table, column, definition in [
            ("usuarios", "nombre", "TEXT NOT NULL DEFAULT 'Paciente'"),
            ("usuarios", "especialidad", "TEXT DEFAULT ''"),
            ("usuarios", "telefono", "TEXT DEFAULT ''"),
            ("usuarios", "activo", "INTEGER DEFAULT 1"),
            ("usuarios", "recuperacion_token", "TEXT"),
            ("citas", "motivo", "TEXT"),
            ("citas", "estado", "TEXT DEFAULT 'pendiente'"),
        ]:
            try:
                cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                conn.commit()
Base.metadata.create_all(bind=engine)
migrate_database()

# ---------------------
# Tareas Programadas (Cron Jobs)
# ---------------------
def enviar_recordatorios_diarios():
    """Busca todas las citas de mañana y envía un WhatsApp automáticamente mediante Green API."""
    db = SessionLocal()
    try:
        manana = (datetime.now().date() + timedelta(days=1))
        
        citas_manana = db.query(Cita).filter(
            Cita.fecha == manana, 
            Cita.estado != "cancelada"
        ).all()
        
        for cita in citas_manana:
            paciente = db.query(Usuario).filter(Usuario.id == cita.paciente_id).first()
            if paciente and paciente.telefono:
                numero_whatsapp = f"52{paciente.telefono}@c.us"
                texto_mensaje = f"Hola, Cita Salud te recuerda que tienes una cita médica confirmada para mañana {cita.fecha} a las {cita.hora_inicio.strftime('%H:%M')}. ¡Te esperamos!"
                
                payload = {
                    "chatId": numero_whatsapp,
                    "message": texto_mensaje
                }
                headers = {'Content-Type': 'application/json'}
                
                response = requests.post(GREEN_API_URL, json=payload, headers=headers)
                if response.status_code != 200:
                    print(f"Error cron WhatsApp Green API: {response.text}")
    finally:
        db.close()

# ---------------------
# Schemas de Pydantic
# ---------------------
class UsuarioCreate(BaseModel):
    nombre: str = Field(..., min_length=3)
    correo: EmailStr
    contrasena: str = Field(..., min_length=6)
    especialidad: Optional[str] = None
    telefono: Optional[str] = None

class PacienteCreate(BaseModel):
    nombre: str = Field(..., min_length=3)
    telefono: str = Field(..., min_length=10)

class UsuarioRead(BaseModel):
    id: int
    nombre: str
    correo: str
    rol: str
    especialidad: Optional[str] = None
    telefono: Optional[str] = None
    model_config = {"from_attributes": True}

class CitaCreate(BaseModel):
    paciente_id: int
    medico_id: int
    fecha: date
    hora_inicio: time
    hora_fin: time
    motivo: Optional[str] = None
    estado: str = Field(default="pendiente")

    @field_validator("estado", mode="before")
    @classmethod
    def validar_estado(cls, value: str) -> str:
        estados_validos = {"pendiente", "confirmada", "cancelada"}
        valor = value.lower().strip()
        if valor not in estados_validos:
            raise ValueError(f"Estado inválido. Use uno de: {estados_validos}")
        return valor

    @model_validator(mode="after")
    def validar_horarios(self) -> "CitaCreate":
        inicio_minutos = _to_minutes(self.hora_inicio)
        fin_minutos = _to_minutes(self.hora_fin)
        if not (8 * 60 <= inicio_minutos <= 21 * 60):
            raise ValueError("Las citas solo pueden agendarse entre las 08:00 y las 21:00")
        if not (8 * 60 <= fin_minutos <= 21 * 60):
            raise ValueError("Las citas solo pueden agendarse entre las 08:00 y las 21:00")
        if fin_minutos <= inicio_minutos:
            raise ValueError("La hora de fin debe ser posterior a la hora de inicio")
        if fin_minutos - inicio_minutos != 30:
            raise ValueError("Cada cita debe tener una duración de 30 minutos")
        return self

class CitaRead(BaseModel):
    id: int
    paciente_id: int
    medico_id: int
    fecha: date
    hora_inicio: time
    hora_fin: time
    motivo: Optional[str]
    estado: str
    model_config = {"from_attributes": True}

# ---------------------
# Aplicación FastAPI
# ---------------------
app = FastAPI(title="CitaSalud API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
def root():
    html_path = static_dir / "index.html"
    return html_path.read_text(encoding="utf-8")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def seed_default_users(db: Session) -> None:
    if db.query(Usuario).filter(Usuario.rol == "medico").count() == 0:
        medicos = [
            {"nombre": "Dr. Ana Pérez", "correo": "ana.perez@clinica.com", "contrasena_hash": hash_password("medico123"), "rol": "medico", "especialidad": "Cardiología"},
            {"nombre": "Dr. Carlos Gómez", "correo": "carlos.gomez@clinica.com", "contrasena_hash": hash_password("medico123"), "rol": "medico", "especialidad": "Dermatología"},
        ]
        for medico in medicos:
            db.add(Usuario(**medico))
    db.commit()

@app.on_event("startup")
def startup_event():
    with SessionLocal() as db:
        seed_default_users(db)
        
    scheduler = BackgroundScheduler()
    scheduler.add_job(enviar_recordatorios_diarios, 'cron', hour=10, minute=0)
    scheduler.start()

def get_user_by_email(db: Session, email: str) -> Optional[Usuario]:
    return db.query(Usuario).filter(Usuario.correo == email).first()

def authenticate_user(db: Session, email: str, password: str) -> Optional[Usuario]:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.contrasena_hash):
        return None
    if user.rol not in {"operario", "admin"}:
        return None
    return user

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    credentials_exception = HTTPException(
        status_code=401,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_by_email(db, email)
    if user is None:
        raise credentials_exception
    return user

def get_current_active_operario(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.rol not in {"operario", "admin"}:
        raise HTTPException(status_code=403, detail="Se requiere rol de operario")
    if current_user.activo != 1:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user

# ---------------------
# Endpoints de usuario
# ---------------------
@app.post("/usuarios", response_model=UsuarioRead, status_code=201)
def crear_usuario(paciente: PacienteCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    correo_falso = f"paciente_{uuid4().hex[:8]}@citasalud.com"
    nuevo_usuario = Usuario(
        nombre=paciente.nombre,
        correo=correo_falso,
        contrasena_hash=hash_password("paciente1234"),
        rol="paciente",
        especialidad="",
        telefono=paciente.telefono,
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return nuevo_usuario

@app.get("/usuarios", response_model=List[UsuarioRead])
def listar_usuarios(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    return db.query(Usuario).order_by(Usuario.id).all()

@app.get("/setup/status")
def setup_status(db: Session = Depends(get_db)):
    has_operario = db.query(Usuario).filter(Usuario.rol == "operario").count() > 0
    return {"has_operario": has_operario}

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    correo: Optional[str] = None

@app.post("/operarios/register", response_model=Token)
def register_operario(operario: UsuarioCreate, db: Session = Depends(get_db)):
    existing = db.query(Usuario).filter(Usuario.correo == operario.correo).first()
    if existing:
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
    nuevo_operario = Usuario(
        nombre=operario.nombre,
        correo=operario.correo,
        contrasena_hash=hash_password(operario.contrasena),
        rol="operario",
        especialidad=operario.especialidad or "",
        telefono=operario.telefono or "",
    )
    db.add(nuevo_operario)
    db.commit()
    db.refresh(nuevo_operario)
    
    access_token = create_access_token(data={"sub": nuevo_operario.correo})
    return {"access_token": access_token, "token_type": "bearer"}

class TokenRequest(BaseModel):
    correo: EmailStr
    contrasena: str

class PasswordRecoveryRequest(BaseModel):
    correo: EmailStr

@app.post("/token", response_model=Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if _is_login_blocked(form_data.username, client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos. Intenta más tarde.")
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        _record_failed_login(form_data.username, client_ip)
        raise HTTPException(status_code=401, detail="Correo o contraseña inválida", headers={"WWW-Authenticate": "Bearer"})
    access_token = create_access_token(data={"sub": user.correo})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/login", response_model=Token)
def login_with_json(request: Request, login: TokenRequest, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if _is_login_blocked(login.correo, client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos. Intenta más tarde.")
    
    user = authenticate_user(db, login.correo, login.contrasena)
    if not user:
        _record_failed_login(login.correo, client_ip)
        raise HTTPException(status_code=401, detail="Correo o contraseña inválida")
    
    access_token = create_access_token(data={"sub": user.correo})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/recuperar-password")
def recuperar_password(request_data: PasswordRecoveryRequest, db: Session = Depends(get_db)):
    usuario = get_user_by_email(db, request_data.correo)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    token = str(uuid4())
    usuario.recuperacion_token = token
    db.add(usuario)
    db.commit()
    return {"detail": "Correo de recuperación enviado", "token": token}

# ---------------------
# Endpoints de WhatsApp Green API
# ---------------------
@app.post("/whatsapp/remind/{cita_id}")
def enviar_recordatorio_individual(cita_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    """Envía un recordatorio de WhatsApp a una cita en específico de forma manual mediante Green API."""
    cita = db.query(Cita).filter(Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    paciente = db.query(Usuario).filter(Usuario.id == cita.paciente_id).first()
    if not paciente or not paciente.telefono:
        raise HTTPException(status_code=400, detail="El paciente de esta cita no tiene un número de teléfono registrado")
    
    # Formatear el número para Green API (código de país + número + sufijo)
    numero_whatsapp = f"52{paciente.telefono}@c.us"
    texto_mensaje = f"Hola, Cita Salud te recuerda que tienes una cita médica confirmada para el {cita.fecha} a las {cita.hora_inicio.strftime('%H:%M')}. ¡Te esperamos!"

    payload = {
        "chatId": numero_whatsapp,
        "message": texto_mensaje
    }
    
    headers = {
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(GREEN_API_URL, json=payload, headers=headers)
        if response.status_code == 200:
            return {"detail": "¡Recordatorio enviado con éxito!"}
        else:
            raise HTTPException(status_code=400, detail=f"Error al enviar mensaje: {response.text}")
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@app.get("/whatsapp/webhook")
def verify_webhook(request: Request):
    """Mantenido por si en el futuro se configura un Webhook en Green API"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode and token:
        if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
            return int(challenge)
    raise HTTPException(status_code=403, detail="Token de verificación inválido")

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Mantenido para procesamiento de mensajes entrantes (requeriría adaptarlo a la estructura JSON de Green API)"""
    body = await request.json()
    try:
        entry = body['entry'][0]
        changes = entry['changes'][0]
        value = changes['value']
        
        if 'messages' in value:
            message = value['messages'][0]
            telefono_paciente = message['from']
            texto_respuesta = message['text']['body'].strip()
            
            paciente = db.query(Usuario).filter(Usuario.telefono == telefono_paciente).first()
            if paciente:
                manana = (datetime.now().date() + timedelta(days=1))
                cita = db.query(Cita).filter(Cita.paciente_id == paciente.id, Cita.fecha == manana).first()
                
                if cita:
                    if texto_respuesta == "1":
                        cita.estado = "confirmada"
                    elif texto_respuesta == "2":
                        cita.estado = "cancelada"
                    
                    db.add(cita)
                    db.commit()
    except KeyError:
        pass
    
    return {"status": "ok"}

@app.get("/operarios", response_model=List[UsuarioRead])
def listar_operarios(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    return db.query(Usuario).filter(Usuario.rol == "operario").all()

@app.get("/operario/me", response_model=UsuarioRead)
def obtener_operario_actual(current_user: Usuario = Depends(get_current_active_operario)):
    return current_user

@app.post("/citas/{cita_id}/cancelar")
def cancelar_cita(cita_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    cita = db.query(Cita).filter(Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    cita.estado = "cancelada"
    db.add(cita)
    db.commit()
    return {"detail": "Cita cancelada", "cita_id": cita.id}

@app.delete("/citas/{cita_id}")
def eliminar_cita(cita_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    cita = db.query(Cita).filter(Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    db.delete(cita)
    db.commit()
    return {"detail": "Cita eliminada", "cita_id": cita_id}

@app.get("/medicos", response_model=List[UsuarioRead])
def listar_medicos(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    return db.query(Usuario).filter(Usuario.rol == "medico").all()

# ---------------------
# Endpoints de citas
# ---------------------
@app.post("/citas", response_model=CitaRead, status_code=201)
def crear_cita(cita: CitaCreate, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    medico = db.query(Usuario).filter(Usuario.id == cita.medico_id, Usuario.rol == "medico").first()
    paciente = db.query(Usuario).filter(Usuario.id == cita.paciente_id, Usuario.rol == "paciente").first()
    
    if not medico:
        raise HTTPException(status_code=404, detail="Médico no encontrado o no es un médico válido")
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente no encontrado o no es un paciente válido")
    
    nuevo_inicio = _to_minutes(cita.hora_inicio)
    nuevo_fin = _to_minutes(cita.hora_fin)
    citas_existentes = db.query(Cita).filter(Cita.medico_id == cita.medico_id, Cita.fecha == cita.fecha).all()
    
    conflicto = any(
        _to_minutes(existing.hora_inicio) < nuevo_fin and nuevo_inicio < _to_minutes(existing.hora_fin)
        for existing in citas_existentes
    )
    if conflicto:
        raise HTTPException(status_code=400, detail="El médico ya tiene una cita en ese horario")
    
    nueva_cita = Cita(
        paciente_id=cita.paciente_id,
        medico_id=cita.medico_id,
        fecha=cita.fecha,
        hora_inicio=cita.hora_inicio,
        hora_fin=cita.hora_fin,
        motivo=cita.motivo,
        estado=cita.estado,
    )
    db.add(nueva_cita)
    db.commit()
    db.refresh(nueva_cita)
    return nueva_cita

@app.get("/citas", response_model=List[CitaRead])
def listar_citas(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    return db.query(Cita).order_by(Cita.fecha, Cita.hora_inicio).all()

@app.get("/citas/medico/{medico_id}", response_model=List[CitaRead])
def listar_citas_medico(medico_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    return db.query(Cita).filter(Cita.medico_id == medico_id).order_by(Cita.fecha, Cita.hora_inicio).all()

@app.get("/citas/paciente/{paciente_id}", response_model=List[CitaRead])
def listar_citas_paciente(paciente_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    return db.query(Cita).filter(Cita.paciente_id == paciente_id).order_by(Cita.fecha, Cita.hora_inicio).all()

@app.get("/citas/{cita_id}", response_model=CitaRead)
def obtener_cita(cita_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_active_operario)):
    cita = db.query(Cita).filter(Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    return cita