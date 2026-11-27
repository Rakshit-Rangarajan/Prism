import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import {SignIn} from './SignIn';
import './style.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><SignIn>{logout=><App onSignOut={logout}/>}</SignIn></React.StrictMode>);
