import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Repository from './pages/Repository';
import Upload from './pages/Upload';
import Extraction from './pages/Extraction';
import Verification from './pages/Verification';
import Approvals from './pages/Approvals';
import Maintenance from './pages/Maintenance';
import Assistant from './pages/Assistant';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Unauthenticated Route */}
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Navigate to="/login" replace />} />

        {/* Authenticated Layout Routes */}
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/repository" element={<Repository />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/extraction" element={<Extraction />} />
          <Route path="/verification" element={<Verification />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/master-maintenance" element={<Maintenance />} />
        </Route>

        {/* Fallback route */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
