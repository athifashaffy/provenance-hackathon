import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './index.css';
import Layout from './components/Layout.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Supplier from './pages/Supplier.jsx';
import Purchaser from './pages/Purchaser.jsx';

// Base path the app is served under (Vite's `base`, e.g. "/aegis/" or "/").
// React Router wants it without a trailing slash.
const basename = import.meta.env.BASE_URL.replace(/\/$/, '');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/supplier" element={<Supplier />} />
          <Route path="/purchaser" element={<Purchaser />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
