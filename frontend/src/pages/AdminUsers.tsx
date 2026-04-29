import { useEffect, useState } from "react";
import { createUser, deleteUser, listUsers, updateUser } from "../api/admin";
import { AppRole, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { canViewRules } from "../auth/permissions";

const ROLE_OPTIONS: AppRole[] = ["admin", "model_engineer", "operator"];

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export default function AdminUsers() {
  const { user } = useAuth();
  const isAdmin = canViewRules(user);

  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<AppRole>("operator");

  const load = async () => {
    try {
      setError(null);
      setUsers(await listUsers());
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  useEffect(() => {
    if (!isAdmin) {
      return;
    }
    void load();
  }, [isAdmin]);

  const handleCreate = async () => {
    if (!email.trim() || !username.trim() || !password.trim()) {
      setError("Email, username and password are required.");
      return;
    }

    try {
      setError(null);
      await createUser({
        email: email.trim(),
        username: username.trim(),
        password,
        full_name: fullName.trim() || undefined,
        role,
      });
      setEmail("");
      setUsername("");
      setPassword("");
      setFullName("");
      setRole("operator");
      await load();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const toggleActive = async (target: User) => {
    try {
      setError(null);
      await updateUser(target.id, { is_active: !target.is_active });
      await load();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const changeRole = async (target: User, nextRole: AppRole) => {
    try {
      setError(null);
      await updateUser(target.id, { role: nextRole });
      await load();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  const removeUser = async (userId: number) => {
    if (!window.confirm(`Delete user #${userId}?`)) {
      return;
    }
    try {
      setError(null);
      await deleteUser(userId);
      await load();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  if (!isAdmin) {
    return (
      <div className="card">
        <h2>User Management</h2>
        <p className="small">Only admin users can manage users.</p>
      </div>
    );
  }

  return (
    <div className="grid">
      <div className="card">
        <h2>User Management</h2>
        {error && <p className="small">{error}</p>}
        <div className="form-row">
          <input className="input" placeholder="Email" value={email} onChange={(event) => setEmail(event.target.value)} />
          <input className="input" placeholder="Username" value={username} onChange={(event) => setUsername(event.target.value)} />
          <input className="input" type="password" placeholder="Password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </div>
        <div className="form-row">
          <input className="input" placeholder="Full name (optional)" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          <select className="input" value={role} onChange={(event) => setRole(event.target.value as AppRole)}>
            {ROLE_OPTIONS.map((roleOption) => (
              <option key={roleOption} value={roleOption}>{roleOption}</option>
            ))}
          </select>
          <button className="button" onClick={() => void handleCreate()}>Create user</button>
        </div>
      </div>

      <div className="card">
        <h3>Existing Users</h3>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Username</th>
              <th>Email</th>
              <th>Role</th>
              <th>Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.username}</td>
                <td>{item.email}</td>
                <td>
                  <select className="input" value={item.role} onChange={(event) => void changeRole(item, event.target.value as AppRole)}>
                    {ROLE_OPTIONS.map((roleOption) => (
                      <option key={roleOption} value={roleOption}>{roleOption}</option>
                    ))}
                  </select>
                </td>
                <td>{item.is_active ? "Yes" : "No"}</td>
                <td>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="button secondary" onClick={() => void toggleActive(item)}>
                      {item.is_active ? "Disable" : "Enable"}
                    </button>
                    <button className="button secondary" onClick={() => void removeUser(item.id)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
