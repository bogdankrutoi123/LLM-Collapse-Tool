import { useEffect, useState } from "react";
import { listAuditLogs } from "../api/admin";
import { AuditLog } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { canViewRules } from "../auth/permissions";

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export default function AdminAudit() {
  const { user } = useAuth();
  const isAdmin = canViewRules(user);

  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) {
      return;
    }

    listAuditLogs()
      .then(setLogs)
      .catch((error: unknown) => setError(getErrorMessage(error)));
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="card">
        <h2>Audit Log</h2>
        <p className="small">Only admin users can access audit logs.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Audit Log</h2>
      {error && <p className="small">{error}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Time</th>
            <th>User ID</th>
            <th>Action</th>
            <th>Entity</th>
            <th>Entity ID</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((entry) => (
            <tr key={entry.id}>
              <td>{new Date(entry.timestamp).toLocaleString()}</td>
              <td>{entry.user_id ?? "-"}</td>
              <td>{entry.action}</td>
              <td>{entry.entity_type}</td>
              <td>{entry.entity_id ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
