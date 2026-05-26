import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';

const TopNavBar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabClass = (path) => {
    const isActive = location.pathname.startsWith(path);
    return `font-semibold text-sm pb-2 transition-all ${
      isActive 
        ? 'text-primary border-b-2 border-primary' 
        : 'text-on-surface-variant hover:text-primary'
    }`;
  };

  return (
    <header className="fixed top-0 left-0 w-full z-50 bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center h-14 px-lg shadow-sm">
      <div className="flex items-center gap-md">
        <span 
          onClick={() => navigate('/dashboard')}
          className="text-xl font-bold text-primary mr-4 cursor-pointer select-none"
        >
          ContractLens Manager
        </span>
        <nav className="hidden md:flex gap-lg h-full items-center pt-2">
          <Link to="/dashboard" className={getTabClass('/dashboard')}>
            Dashboard
          </Link>
          <Link to="/repository" className={getTabClass('/repository')}>
            Repository
          </Link>
          <Link to="/assistant" className={getTabClass('/assistant')}>
            Assistant
          </Link>
          <Link to="/approvals" className={getTabClass('/approvals')}>
            Approvals
          </Link>
        </nav>
      </div>
      
      <div className="flex items-center gap-md">
        <div className="relative hidden lg:block">
          <span className="material-symbols-outlined absolute left-sm top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">
            search
          </span>
          <input 
            className="bg-surface-container-low border-none rounded-lg pl-xl pr-md py-xs text-sm w-64 focus:ring-1 focus:ring-primary outline-none transition-all" 
            placeholder="Search contracts..." 
            type="text" 
          />
        </div>
        
        <button 
          onClick={() => navigate('/upload')} 
          className="bg-primary text-on-primary px-md py-sm rounded-lg text-sm font-semibold hover:opacity-90 active:scale-95 transition-all"
        >
          Upload
        </button>
        
        <div className="flex gap-sm">
          <span className="material-symbols-outlined text-on-surface-variant cursor-pointer hover:text-primary transition-colors">
            notifications
          </span>
          <span className="material-symbols-outlined text-on-surface-variant cursor-pointer hover:text-primary transition-colors">
            settings
          </span>
        </div>
        
        <img 
          alt="User Profile" 
          className="w-8 h-8 rounded-full border border-outline-variant object-cover" 
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuBPQTZB1agwQ5PTYV5FtJnMz5cCs98G0P77KO0d9Lar7RjiHkc22LS2e-gOmbgfoMDyp9w3h-yqqo-zj4cwh5PDiTSu-qfjB4fqCEHxQEtNZHoF_LlhkTNFHWT1PMZ4kfradpR6Wjzgs2SKRZEpZNeygURQ1pCZZO-85VqKK_bx8WNZZtclbK_kmes-ReOz8u01O2Y7Fwsu54jbFBjKvSw4sOaCBzNHv17IW59QXArgRKZBtwbIzrzuHF3R7ZMLTZ0_2hN7B58TsjTu" 
        />
      </div>
    </header>
  );
};

export default TopNavBar;
