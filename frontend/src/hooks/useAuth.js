import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const makeUserId = (username) => {
  const cleaned = (username || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');
  return cleaned ? `user_${cleaned}` : `user_${Date.now()}`;
};

export const useAuth = () => {
  const navigate = useNavigate();
  const [role, setRole] = useState('operation_user');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  const canSubmit = useMemo(
    () => Boolean(username.trim()) && Boolean(password.trim()),
    [username, password]
  );

  const togglePasswordVisibility = useCallback(() => {
    setShowPassword((prev) => !prev);
  }, []);

  const handleLogin = useCallback(
    async (event) => {
      event.preventDefault();
      setError('');

      if (!canSubmit) {
        setError('Username and password are required.');
        return;
      }

      const userData = {
        id: makeUserId(username),
        email: username,
        name: username.split('@')[0] || username,
        role,
      };

      localStorage.setItem('currentUser', JSON.stringify(userData));
      localStorage.setItem('authToken', `token_${Date.now()}`);
      localStorage.setItem('rememberMe', rememberMe ? '1' : '0');
      navigate('/dashboard');
    },
    [canSubmit, navigate, rememberMe, role, username]
  );

  return {
    role,
    setRole,
    username,
    setUsername,
    password,
    setPassword,
    rememberMe,
    setRememberMe,
    showPassword,
    togglePasswordVisibility,
    error,
    setError,
    handleLogin,
  };
};

export default useAuth;
