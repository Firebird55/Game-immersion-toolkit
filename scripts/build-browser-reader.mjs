import {build} from 'vite';
import {fileURLToPath} from 'node:url';
export async function buildBrowserReader(){
 await build({configFile:false,publicDir:false,define:{'process.env.NODE_ENV':'"production"'},logLevel:'warn',build:{target:'es2022',outDir:'public/mobile-capture',emptyOutDir:false,minify:true,cssCodeSplit:false,lib:{entry:fileURLToPath(new URL('../mobile/companion.jsx',import.meta.url)),formats:['es'],fileName:()=> 'companion.js',cssFileName:'companion'},rollupOptions:{onwarn(warning,warn){if(warning.code!=='MODULE_LEVEL_DIRECTIVE')warn(warning);},output:{assetFileNames:'companion.[ext]'}}}});
}
if(process.argv[1]===fileURLToPath(import.meta.url))await buildBrowserReader();
