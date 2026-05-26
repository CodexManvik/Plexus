import React from 'react';
import useAuth from '../hooks/useAuth';

const Login = () => {
  const {
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
    handleLogin
  } = useAuth();

  return (
    <div className="min-h-screen flex items-center justify-center p-md bg-surface-container-low login-mesh font-sans">
      <main className="w-full max-w-[440px] flex flex-col gap-lg animate-fadeIn">
        
        {/* Branding Section */}
        <header className="flex flex-col items-center text-center gap-sm">
          <div className="flex items-center gap-xs select-none">
            <span className="material-symbols-outlined text-primary text-[32px]" style={{ fontVariationSettings: '"FILL" 1' }}>
              gavel
            </span>
            <h1 className="text-3xl font-black text-primary tracking-tighter">ContractLens</h1>
          </div>
          <p className="text-xs text-on-surface-variant uppercase tracking-widest font-bold">
            Enterprise Contract Intelligence
          </p>
        </header>

        {/* Form Card */}
        <section className="bg-surface-container-lowest border border-outline-variant rounded-lg p-xl shadow-md">
          <div className="mb-lg">
            <h2 className="text-xl font-bold text-primary mb-xs">Welcome back</h2>
            <p className="text-sm text-on-surface-variant">
              Please enter your credentials to access the legal repository.
            </p>
          </div>

          <form className="space-y-md" onSubmit={handleLogin}>
            {error && (
              <div className="p-sm bg-error-container text-on-error-container text-xs rounded border border-error/20 flex items-center gap-xs font-semibold">
                <span className="material-symbols-outlined text-[16px]">error</span>
                {error}
              </div>
            )}

            {/* Role Selection */}
            <div className="space-y-xs">
              <label className="text-xs font-bold text-on-surface flex items-center gap-xs select-none" htmlFor="role">
                <span className="material-symbols-outlined text-[16px]">account_tree</span>
                SYSTEM ROLE
              </label>
              <div className="relative">
                <select 
                  className="w-full bg-surface-container-low border-b-2 border-outline-variant focus:border-primary py-sm px-md appearance-none outline-none font-semibold text-body-md transition-colors" 
                  id="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                >
                  <option value="admin">Admin</option>
                  <option value="operation_user">Operation User</option>
                  <option value="operation_head">Operation Head</option>
                </select>
                <div className="absolute right-md top-1/2 -translate-y-1/2 pointer-events-none">
                  <span className="material-symbols-outlined text-on-surface-variant">expand_more</span>
                </div>
              </div>
            </div>

            {/* Username */}
            <div className="space-y-xs">
              <label className="text-xs font-bold text-on-surface flex items-center gap-xs select-none" htmlFor="username">
                <span className="material-symbols-outlined text-[16px]">person</span>
                USERNAME
              </label>
              <input 
                className="w-full bg-surface-container-low border-b-2 border-outline-variant focus:border-primary py-sm px-md outline-none text-body-md placeholder:text-outline transition-colors" 
                id="username" 
                placeholder="e.g. j.doe@firm.com" 
                type="text" 
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            {/* Password */}
            <div className="space-y-xs">
              <div className="flex justify-between items-center select-none">
                <label className="text-xs font-bold text-on-surface flex items-center gap-xs" htmlFor="password">
                  <span className="material-symbols-outlined text-[16px]">lock</span>
                  PASSWORD
                </label>
                <a className="text-xs font-bold text-primary hover:underline transition-all" href="#">Forgot?</a>
              </div>
              <div className="relative">
                <input 
                  className="w-full bg-surface-container-low border-b-2 border-outline-variant focus:border-primary py-sm px-md outline-none text-body-md placeholder:text-outline transition-colors" 
                  id="password" 
                  placeholder="••••••••" 
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button 
                  type="button" 
                  onClick={togglePasswordVisibility} 
                  className="absolute right-md top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors"
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {showPassword ? 'visibility_off' : 'visibility'}
                  </span>
                </button>
              </div>
            </div>

            {/* Remember Me */}
            <div className="flex items-center gap-sm pt-xs select-none">
              <input 
                className="w-4 h-4 rounded-sm border-outline-variant text-primary focus:ring-primary-container focus:ring-1" 
                id="remember" 
                type="checkbox" 
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              <label htmlFor="remember" className="text-xs font-semibold text-on-surface-variant cursor-pointer">
                Remember this device for 30 days
              </label>
            </div>

            {/* Submit Button */}
            <button 
              className="w-full bg-primary text-on-primary font-bold text-xs py-md rounded-lg hover:opacity-90 active:scale-[0.98] transition-all flex items-center justify-center gap-sm mt-lg shadow-sm" 
              type="submit"
            >
              <span>SECURE ACCESS</span>
              <span className="material-symbols-outlined text-[18px]">login</span>
            </button>
          </form>
        </section>

        {/* Footer / Trust Badges */}
        <footer className="flex flex-col items-center gap-md opacity-60 mt-md">
          <div className="flex items-center gap-lg">
            <div className="flex items-center gap-xs">
              <span className="material-symbols-outlined text-[16px]">verified_user</span>
              <span className="text-[10px] font-bold tracking-wider">SOC2 COMPLIANT</span>
            </div>
            <div className="flex items-center gap-xs">
              <span className="material-symbols-outlined text-[16px]">encrypted</span>
              <span className="text-[10px] font-bold tracking-wider">AES-256 ENCRYPTION</span>
            </div>
          </div>
          <nav className="flex gap-md select-none">
            <a className="text-[11px] font-bold text-on-surface-variant hover:text-primary transition-colors" href="#">Privacy Policy</a>
            <a className="text-[11px] font-bold text-on-surface-variant hover:text-primary transition-colors" href="#">Terms of Service</a>
            <a className="text-[11px] font-bold text-on-surface-variant hover:text-primary transition-colors" href="#">Support</a>
          </nav>
        </footer>

      </main>
    </div>
  );
};

export default Login;
