import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { Notification } from "../api/types";

export default function Notifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Notification[]>("/api/v1/notifications/")
      .then(setNotifications)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="card">
      <h2>Notifications</h2>
      {error && <p className="small">{error}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {notifications.map((item) => (
            <tr key={item.id}>
              <td>{item.id}</td>
              <td>{item.title}</td>
              <td>{item.severity}</td>
              <td>{item.status}</td>
              <td>{new Date(item.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
