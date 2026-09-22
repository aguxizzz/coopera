import { Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import TenantPortal from "./pages/TenantPortal";
import AdminLogin from "./pages/AdminLogin";
import AdminDashboard from "./pages/AdminDashboard";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/:tenantSlug/admin/dashboard" element={<AdminDashboard />} />
      <Route path="/:tenantSlug/admin" element={<AdminLogin />} />
      <Route path="/:tenantSlug" element={<TenantPortal />} />
    </Routes>
  );
}

export default App;
