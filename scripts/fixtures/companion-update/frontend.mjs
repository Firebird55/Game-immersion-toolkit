import http from 'node:http';
const port=Number(process.argv[process.argv.indexOf('--port')+1]);
http.createServer((_request,response)=>response.end('prepared frontend')).listen(port,'127.0.0.1');
