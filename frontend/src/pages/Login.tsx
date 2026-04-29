import { useState } from "react";
import { loginUser } from "../api/auth";
import { useAuth } from "../auth/AuthContext";
import { useNavigate, Link } from "react-router-dom";

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const user = await loginUser(username, password);
      login(user);
      navigate("/overview");
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  return (
    <div className="auth-container">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h2>Sign in</h2>
        {error && <p className="small">{error}</p>}
        <label className="small">Username</label>
        <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} />
        <label className="small">Password</label>
        <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button className="button" type="submit">Login</button>
        <p className="small">No account? <Link to="/register">Register</Link></p>
      </form>
    </div>
  );
}
