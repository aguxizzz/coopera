export default function PrivacyPolicy() {
  return (
    <div className="legal-page">
      <div className="legal-content">
        <h1>Política de privacidad</h1>
        <p className="muted">Última actualización: 3 de octubre de 2026</p>

        <p>
          Esta política describe qué información recolecta la aplicación móvil de
          Coopera para gestores de consumos ("la app") y cómo se utiliza.
        </p>

        <h2>Quiénes somos</h2>
        <p>
          Coopera es una plataforma utilizada por cooperativas de servicios para
          gestionar socios, lecturas de medidores y facturación. La app está
          destinada a los gestores (empleados de la cooperativa) que realizan
          lecturas de consumo en el domicilio de los socios.
        </p>

        <h2>Información que recolectamos</h2>
        <ul>
          <li>
            <strong>Cámara:</strong> la app usa la cámara para fotografiar el visor
            del medidor como respaldo de la lectura registrada. Las fotos se asocian
            a la lectura y al socio correspondiente.
          </li>
          <li>
            <strong>Ubicación:</strong> la app usa la ubicación del dispositivo para
            validar que la lectura se tomó en el domicilio del socio. No se rastrea
            la ubicación fuera de ese momento puntual.
          </li>
          <li>
            <strong>Cuenta de gestor:</strong> email y credenciales de acceso del
            gestor, usados exclusivamente para autenticación dentro de la
            cooperativa que lo emplea.
          </li>
        </ul>

        <h2>Cómo usamos esta información</h2>
        <p>
          La información recolectada se usa únicamente para el funcionamiento del
          servicio: registrar lecturas de consumo, respaldarlas con una foto y
          verificar que se tomaron en el domicilio correcto. No vendemos ni
          compartimos esta información con terceros ajenos a la cooperativa
          correspondiente.
        </p>

        <h2>Almacenamiento y retención</h2>
        <p>
          Las fotos y lecturas se almacenan en los servidores de Coopera asociados
          a la cooperativa del gestor, y se conservan mientras sea necesario para
          la gestión de facturación y auditoría de consumos.
        </p>

        <h2>Tus derechos</h2>
        <p>
          Si sos socio de una cooperativa que usa Coopera y querés conocer, corregir
          o solicitar la eliminación de tus datos, podés contactar directamente a tu
          cooperativa, quien es responsable de tus datos frente a Coopera.
        </p>

        <h2>Contacto</h2>
        <p>
          Para consultas sobre esta política, escribinos a{" "}
          <a href="mailto:soporte@coopera.app">soporte@coopera.app</a>.
        </p>
      </div>
    </div>
  );
}
