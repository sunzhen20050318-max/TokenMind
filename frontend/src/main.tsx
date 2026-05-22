import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { AuthGate } from './components/AuthGate/AuthGate';
import { installFetchAuthInterceptor } from './services/apiAuth';
import './index.css';

// Inject X-TokenMind-Secret on every /api or /ws fetch before any component
// mounts so even the first /api/config call carries the header.
installFetchAuthInterceptor();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthGate>
      <App />
    </AuthGate>
  </React.StrictMode>
);
