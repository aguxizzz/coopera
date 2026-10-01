# Coopera — prototipo

Plataforma multi-tenant para que cooperativas de servicios gestionen socios,
consumos y deudas, y para que cada socio consulte su saldo y descargue su
boleta. Pensada para escalar a más de una cooperativa desde el día uno.

## Arquitectura

- **Backend**: FastAPI + SQLAlchemy. `backend/app`
- **Frontend**: React (Vite) + React Router. `frontend/`
- **DB**: SQLite por defecto para correr el prototipo sin fricción
  (`backend/coopera.db`). El modelo ya es compatible con Postgres —
  `docker-compose.yml` en la raíz levanta un Postgres local; para usarlo,
  descomentá `DATABASE_URL` en `backend/.env`.

### Multi-tenancy

Cada cooperativa es un `Tenant` (tabla `tenants`) con su propio `slug`. Hoy el
routing es por path (`/api/t/{slug}/...`, y en el frontend `/valle-verde`)
porque alcanza para el prototipo. El modelo ya tiene
`custom_domain` reservado: pasar a resolver el tenant por el header `Host` en
vez de por el path (`backend/app/deps.py::get_tenant`) es el único lugar que
habría que tocar para que cada cooperativa tenga su propio dominio en
producción — ningún router ni página necesita cambiar.

### Fuente de verdad de los datos

En vez de parsear boletas en PDF (como el sistema anterior), la cooperativa
sube una planilla (.csv o .xlsx) una vez por mes con las columnas:

```
numero_socio, nombre, identificador, consumo, monto, vencimiento (opcional)
```

El admin indica el año/mes del período al subir el archivo. La importación
(`backend/app/services/importer.py`) crea o actualiza cada socio y crea/reemplaza
su factura de ese período. El saldo total de un socio es la suma de sus
facturas no pagadas — se recalcula solo, no se importa como campo aparte.

Esto está pensado para ampliarse a otras fuentes (API del sistema interno de
la cooperativa, carga manual, etc.) sin tocar el resto: alcanza con agregar
otro "importer" que termine escribiendo `Member` + `Invoice`.

### Pagos (Mercado Pago)

Cada cooperativa conecta **su propia** cuenta de Mercado Pago vía OAuth
("Mercado Pago Connect") desde Configuración en el panel admin — el dinero se
acredita directamente en su cuenta, Coopera nunca lo recibe ni guarda sus
credenciales de MP en texto plano (se guardan encriptadas con Fernet,
derivando la clave de `JWT_SECRET`).

Flujo (`backend/app/services/mercadopago.py` + `backend/app/routers/mp.py`):

1. El admin hace clic en "Conectar con Mercado Pago" → se lo redirige a MP
   con un `state` firmado que identifica al tenant.
2. MP redirige de vuelta a `GET /api/mp/oauth/callback` (una única URL fija,
   registrada en la aplicación de MP) → se intercambia el `code` por un
   access/refresh token que se guardan en el `Tenant`.
3. El socio hace clic en "Pagar" (`TenantPortal`) → `POST
   /api/t/{slug}/invoices/{id}/pay` crea una preferencia de Checkout Pro con
   el token del tenant (renovándolo solo si está por vencer) y lo redirige al
   `init_point`.
4. Mercado Pago notifica el pago a `POST /api/t/{slug}/mp/webhook` →
   se consulta el pago con el token del tenant y, si está aprobado, se marca
   `Invoice.pagado = True`.

Para habilitarlo hay que crear **una** aplicación en el [panel de
desarrolladores de Mercado Pago](https://www.mercadopago.com.ar/developers/panel/app)
(para todo el deployment de Coopera, no una por cooperativa), registrar
`PUBLIC_BASE_URL/api/mp/oauth/callback` como redirect URI, y completar
`MP_CLIENT_ID` / `MP_CLIENT_SECRET` en `backend/.env` (ver `.env.example`).
Mientras no estén configuradas, el botón de conectar simplemente no aparece
habilitado — el alias/CBU manual (`Tenant.mp_alias`) sigue funcionando como
alternativa u opción de respaldo.

## Correr el prototipo

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head  # crea/actualiza el esquema de la DB
python seed.py        # crea la cooperativa demo con socios y datos de ejemplo
uvicorn app.main:app --reload --port 8000
```

### Migraciones (Alembic)

El esquema se versiona con Alembic (`backend/alembic/`), no con el modelo de
SQLAlchemy directamente. `alembic/env.py` toma la URL de conexión de
`app.config.settings`, así que usa la misma DB que la app (SQLite o Postgres
según `DATABASE_URL`).

```bash
cd backend
alembic upgrade head                        # aplicar migraciones pendientes
alembic revision --autogenerate -m "algo"   # generar una migración tras cambiar app/models.py
alembic downgrade -1                        # revertir la última
```

Siempre revisá a mano la migración autogenerada antes de commitear: Alembic no
detecta renombres de columnas/tablas (los ve como drop + add) ni cambios de
tipo en SQLite de forma perfecta.

Admin demo: `admin@valleverde.coop` / `coopera123` (tenant `valle-verde`).
Socio demo: número de socio `201`, DNI `29888777` (valle-verde).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Abrí `http://localhost:5173` — redirige directo al portal del socio de la
cooperativa demo (`/valle-verde`); el panel admin está en
`http://localhost:5173/valle-verde/admin`.

## Qué falta para producción

- Autenticación de admin por rol/permisos (hoy es un solo admin por tenant).
- Alta de tenants vía un panel superadmin (hoy se crean con `seed.py` o
  directo en la DB).
- Resolución de tenant por dominio propio en vez de por path.
- Notificaciones (email/WhatsApp) al socio cuando se sube una planilla nueva.
- Tests automatizados (no hay ninguno todavía).
- Validar la firma `x-signature` de los webhooks de Mercado Pago (hoy se
  confía en el `payment_id` y se re-consulta el pago, que ya es razonablemente
  seguro, pero MP recomienda además validar la firma del request).
