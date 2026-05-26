import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import TopNavBar from './TopNavBar';
import SideNavBar from './SideNavBar';

const Layout = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggleCollapse = () => {
    setIsCollapsed(prev => !prev);
  };

  return (
    <div className="min-h-screen bg-background font-sans">
      {/* Top Navbar */}
      <TopNavBar />

      {/* Collapsible Left Sidebar */}
      <SideNavBar isCollapsed={isCollapsed} toggleCollapse={toggleCollapse} />

      {/* Main Content Area */}
      <main 
        className={`pt-14 p-lg min-h-screen transition-all duration-300 ease-in-out ${
          isCollapsed ? 'ml-16' : 'ml-sidebar-width'
        }`}
      >
        <div className="max-w-[1400px] mx-auto animate-fadeIn">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Layout;
