export {default} from '../retired-mobile-service.mjs';
// Keep the existing class/migration identity so retiring public requests does
// not implicitly delete its namespace or interrupt its authored expiry alarms.
export {PairingRoom} from './worker.mjs';
