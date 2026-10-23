import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';
import { warmUpServer } from './lib/api.js';
import { AuthProvider } from './lib/auth.jsx';
import './index.css';

warmUpServer();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
