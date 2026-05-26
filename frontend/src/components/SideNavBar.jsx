import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';

const SideNavBar = ({ isCollapsed, toggleCollapse }) => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const navItems = [
    { icon: 'dashboard', label: 'Analytics', path: '/dashboard' },
    { icon: 'description', label: 'Contracts', path: '/repository' },
    { icon: 'psychology', label: 'Extraction', path: '/extraction' },
    { icon: 'chat_bubble', label: 'Assistant', path: '/assistant' },
    { icon: 'admin_panel_settings', label: 'Admin', path: '/master-maintenance' },
    { icon: 'fact_check', label: 'Review', path: '/approvals' },
    { icon: 'inventory_2', label: 'Archive', path: '/repository' }
  ];

  const getLinkClass = (path) => {
    const isActive = location.pathname === path;
    const base = "flex items-center gap-sm px-sm py-sm rounded-lg transition-all duration-200";
    if (isActive) {
      return `${base} bg-secondary-container text-on-secondary-container font-bold shadow-sm`;
    }
    return `${base} text-secondary hover:bg-surface-container-high hover:text-primary`;
  };

  return (
    <aside 
      className={`fixed left-0 top-14 h-[calc(100vh-3.5rem)] z-40 bg-surface border-r border-outline-variant flex flex-col py-md px-sm gap-xs transition-all duration-300 ease-in-out ${
        isCollapsed ? 'w-16' : 'w-sidebar-width'
      }`}
    >
      {/* Brand Header */}
      <div className={`px-sm mb-lg flex flex-col gap-md select-none overflow-hidden transition-all duration-300`}>
        <div className="flex items-center gap-sm">
          <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center text-on-primary-container shrink-0 shadow-sm">
            <span className="material-symbols-outlined" style={{ fontVariationSettings: '"FILL" 1' }}>
              balance
            </span>
          </div>
          {!isCollapsed && (
            <div className="transition-opacity duration-300 ease-in-out opacity-100 whitespace-nowrap">
              <h2 className="text-md font-black text-primary leading-tight">ContractLens</h2>
              <p className="text-[10px] text-on-surface-variant font-bold tracking-widest">ENTERPRISE TIER</p>
            </div>
          )}
        </div>

        {/* Action Button */}
        <button 
          onClick={() => navigate('/upload')} 
          className={`bg-primary text-on-primary py-sm rounded-lg text-sm font-semibold flex items-center justify-center gap-xs hover:opacity-90 active:scale-95 transition-all shadow-sm ${
            isCollapsed ? 'w-10 h-10 p-0 rounded-full' : 'w-full'
          }`}
          title={isCollapsed ? "New Analysis" : ""}
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          {!isCollapsed && <span>New Analysis</span>}
        </button>
      </div>

      {/* Main Navigation links */}
      <nav className="flex-1 flex flex-col gap-xs overflow-y-auto hide-scrollbar">
        {navItems.map((item, idx) => (
          <Link 
            key={idx} 
            to={item.path} 
            className={getLinkClass(item.path)}
            title={isCollapsed ? item.label : ""}
          >
            <span className="material-symbols-outlined shrink-0">{item.icon}</span>
            {!isCollapsed && <span className="text-sm truncate whitespace-nowrap">{item.label}</span>}
          </Link>
        ))}
      </nav>

      {/* Footer / Toggle & Settings */}
      <div className="border-t border-outline-variant pt-sm flex flex-col gap-xs shrink-0">
        <a 
          className="flex items-center gap-sm px-sm py-sm text-secondary hover:bg-surface-container-high hover:text-primary rounded-lg transition-colors" 
          href="#"
          title={isCollapsed ? "Support" : ""}
        >
          <span className="material-symbols-outlined shrink-0">help</span>
          {!isCollapsed && <span className="text-sm whitespace-nowrap">Support</span>}
        </a>
        <Link 
          to="/login" 
          className="flex items-center gap-sm px-sm py-sm text-secondary hover:bg-surface-container-high hover:text-primary rounded-lg transition-colors"
          title={isCollapsed ? "Logout" : ""}
        >
          <span className="material-symbols-outlined shrink-0">logout</span>
          {!isCollapsed && <span className="text-sm whitespace-nowrap">Logout</span>}
        </Link>
        
        {/* Collapsible Trigger */}
        <button 
          onClick={toggleCollapse} 
          className="flex items-center justify-center p-sm mt-xs text-on-surface-variant hover:text-primary hover:bg-surface-container-high rounded-lg transition-all"
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          <span className="material-symbols-outlined transition-transform duration-300">
            {isCollapsed ? 'chevron_right' : 'chevron_left'}
          </span>
        </button>
      </div>
    </aside>
  );
};

export default SideNavBar;
