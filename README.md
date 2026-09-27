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

### Pagos

Hoy se muestra el alias de Mercado Pago del tenant (`Tenant.mp_alias`) para
que el socio pague por fuera. Para integrar pagos dentro de la web (Checkout
Pro / Checkout API de Mercado Pago), el punto de entrada natural es un nuevo
endpoint `POST /api/t/{slug}/invoices/{id}/pay` que cree una preferencia de
pago con las credenciales de Mercado Pago **de ese tenant** (agregar
`mp_access_token` a `Tenant`), y un webhook `POST /api/t/{slug}/mp/webhook`
que marque `Invoice.pagado = True` al confirmarse el pago.

## Correr el prototipo

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed.py        # crea la cooperativa demo con socios y datos de ejemplo
uvicorn app.main:app --reload --port 8000
```

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
- Integración real de pagos (Mercado Pago) y su webhook.
- Notificaciones (email/WhatsApp) al socio cuando se sube una planilla nueva.
