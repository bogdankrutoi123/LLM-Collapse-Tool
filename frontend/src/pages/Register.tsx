import { useEffect, useState } from "react";
import { getAuthBootstrapStatus, registerUser } from "../api/auth";
import { useNavigate, Link } from "react-router-dom";

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

export default function Register() {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [publicRegistrationEnabled, setPublicRegistrationEnabled] = useState(false);
  const [bootstrapAdminAvailable, setBootstrapAdminAvailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getAuthBootstrapStatus()
      .then((status) => {
        setPublicRegistrationEnabled(status.public_registration_enabled);
        setBootstrapAdminAvailable(status.bootstrap_admin_available);
      })
      .catch(() => {
        setPublicRegistrationEnabled(false);
        setBootstrapAdminAvailable(false);
      });
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await registerUser({
        email,
        username,
        password,
        full_name: fullName
      });
      navigate("/login");
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    }
  };

  return (
    <div className="auth-container">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h2>Create account</h2>
        {error && <p className="small">{error}</p>}
        {!publicRegistrationEnabled && (
          <p className="small">
            Public registration is disabled. Contact an administrator to create your account.
            {bootstrapAdminAvailable ? " Bootstrap admin setup is currently available for initial deployment." : ""}
          </p>
        )}
        <label className="small">Email</label>
        <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!publicRegistrationEnabled} />
        <label className="small">Username</label>
        <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} disabled={!publicRegistrationEnabled} />
        <label className="small">Full name</label>
        <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} disabled={!publicRegistrationEnabled} />
        <label className="small">Password</label>
        <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={!publicRegistrationEnabled} />
        <button className="button" type="submit" disabled={!publicRegistrationEnabled}>Register</button>
        <p className="small">Already have an account? <Link to="/login">Sign in</Link></p>
      </form>
    </div>
  );
}
