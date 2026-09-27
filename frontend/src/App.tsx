import { Navigate, Route, Routes } from "react-router-dom";
import TenantPortal from "./pages/TenantPortal";
import AdminLogin from "./pages/AdminLogin";
import AdminDashboard from "./pages/AdminDashboard";
import DevLogin from "./pages/DevLogin";
import DevDashboard from "./pages/DevDashboard";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/valle-verde" replace />} />
      <Route path="/dev/dashboard" element={<DevDashboard />} />
      <Route path="/dev" element={<DevLogin />} />
      <Route path="/:tenantSlug/admin/dashboard" element={<AdminDashboard />} />
      <Route path="/:tenantSlug/admin" element={<AdminLogin />} />
      <Route path="/:tenantSlug" element={<TenantPortal />} />
    </Routes>
  );
}

export default App;
