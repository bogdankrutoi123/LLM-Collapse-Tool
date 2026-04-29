import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Models from "./pages/Models";
import Prompts from "./pages/Prompts";
import Analysis from "./pages/Analysis";
import Benchmark from "./pages/WikiText";
import Notifications from "./pages/Notifications";
import Rules from "./pages/Rules";
import AdminThresholds from "./pages/AdminThresholds";
import AdminUsers from "./pages/AdminUsers";
import AdminAudit from "./pages/AdminAudit";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ProtectedRoute from "./auth/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/models" element={<Models />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="/benchmark" element={<Benchmark />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/rules" element={<Rules />} />
        <Route path="/thresholds" element={<AdminThresholds />} />
        <Route path="/users" element={<AdminUsers />} />
        <Route path="/audit" element={<AdminAudit />} />
      </Route>
    </Routes>
  );
}
