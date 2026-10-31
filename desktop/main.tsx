import {createRoot} from 'react-dom/client';
import Home from '../app/page';
import {observeNativeBrowserLaunch} from './browser-probe';
import './fonts.css';
import '../app/globals.css';
import '@firebird55/lexirise-components/styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('The desktop frontend root is missing. Re-extract the verified application.');
createRoot(root).render(<Home />);
observeNativeBrowserLaunch();
