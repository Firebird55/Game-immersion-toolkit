// Read the installed game's data and run only its dictionary/grammar routines.
const fs = require('node:fs');
const crypto = require('node:crypto');
const vm = require('node:vm');
const readline = require('node:readline');
const acorn = require('acorn');
const debug = message => { if (process.env.HITO_DEBUG) console.error(message); };
const extractorVersion = 3;

const bytes = fs.readFileSync(process.argv[2]);
const archiveHash = crypto.createHash('sha256').update(bytes).digest('hex');
let cachedCatalog;
try {
  const saved = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  if (saved.archive_hash === archiveHash && saved.extractor_version === extractorVersion) cachedCatalog = saved;
} catch {}
const headerSize = bytes.readUInt32LE(4);
const header = JSON.parse(bytes.subarray(16, 16 + bytes.readUInt32LE(12)).toString('utf8'));
const entries = [];
function list(entry, prefix = '') {
  for (const [name, item] of Object.entries(entry.files || {})) {
    if (item.files) list(item, prefix + name + '/');
    else entries.push({name: prefix + name, ...item});
  }
}
list(header);
function read(entry) {
  const start = 8 + headerSize + Number(entry.offset);
  const data = bytes.subarray(start, start + entry.size);
  if (data.length !== entry.size || (entry.integrity?.hash &&
      crypto.createHash('sha256').update(data).digest('hex') !== entry.integrity.hash)) {
    throw new Error('Game archive integrity check failed');
  }
  return data.toString('utf8');
}
const bundleEntry = entries.find(e => /^dist\/app\..*\.js$/.test(e.name) && !e.unpacked);
if (!bundleEntry) throw new Error('Unsupported Hito game archive');
const bundle = read(bundleEntry);
const tree = acorn.parse(bundle, {ecmaVersion: 'latest', sourceType: 'module'});
debug('Parsed game bundle');
const definitions = {};
function statement(node) {
  if (node.type === 'VariableDeclaration') node.declarations.forEach(n => {
    if (n.id.type === 'Identifier' && n.init) definitions[n.id.name] = bundle.slice(n.start, n.end);
  });
  else if (node.type === 'FunctionDeclaration') definitions[node.id.name] = bundle.slice(node.start, node.end);
  else if (node.type === 'ExpressionStatement') statement(node.expression);
  else if (node.type === 'SequenceExpression') node.expressions.forEach(statement);
  else if (node.type === 'AssignmentExpression' && node.left.type === 'Identifier') {
    definitions[node.left.name] = bundle.slice(node.start, node.end);
  }
}
tree.body.forEach(statement);
function expression(name) {
  return acorn.parse(definitions[name], {ecmaVersion: 'latest'}).body[0].expression.right;
}
function keys(name) {
  return expression(name).properties.flatMap(p => p.type === 'SpreadElement'
    ? keys(p.argument.name) : [p.key.name || p.key.value]);
}
function property(node, name) {
  return node.properties.find(p => p.type === 'Property' && (p.key.name || p.key.value) === name);
}
const languageRootName = Object.keys(definitions).find(name => {
  try {
    const node = expression(name);
    return node.type === 'ObjectExpression' && ['english','hanzi','pinyin','chinese']
      .every(key => property(node, key));
  } catch { return false; }
});
if (!languageRootName) throw new Error('Unsupported Hito language table');
const languageRoot = expression(languageRootName);
const englishNode = property(languageRoot, 'english').value;
const hanziNode = property(languageRoot, 'hanzi').value;
if (hanziNode.type !== 'Identifier') throw new Error('Unsupported Hito grammar table');
const context = vm.createContext({tX: Object.fromEntries(keys('tX').map(k => [k, true]))},
  {codeGeneration: {strings: false, wasm: false}});
vm.runInContext(definitions.$, context, {timeout: 1000});

// Minified identifiers change whenever Hito ships a new bundle. Discover the
// dependency closure of the grammar roots instead of pinning one release's
// identifier list. Function-body references are included so generated lines
// keep working after an update, not just the initial table load.
function dependenciesFrom(root) {
  const bindings = new Set();
  function bind(pattern) {
    if (!pattern) return;
    if (pattern.type === 'Identifier') bindings.add(pattern.name);
    else if (pattern.type === 'RestElement') bind(pattern.argument);
    else if (pattern.type === 'AssignmentPattern') bind(pattern.left);
    else if (pattern.type === 'ArrayPattern') pattern.elements.forEach(bind);
    else if (pattern.type === 'ObjectPattern') pattern.properties.forEach(p => bind(p.value || p.argument));
  }
  function collectBindings(node) {
    if (!node || typeof node !== 'object') return;
    if (/Function(?:Declaration|Expression)$/.test(node.type) || node.type === 'ArrowFunctionExpression') {
      if (node.id) bind(node.id);
      node.params.forEach(bind);
    } else if (node.type === 'VariableDeclarator') bind(node.id);
    else if (node.type === 'CatchClause') bind(node.param);
    for (const [key, value] of Object.entries(node)) {
      if (key === 'start' || key === 'end') continue;
      if (Array.isArray(value)) value.forEach(collectBindings);
      else if (value && typeof value === 'object') collectBindings(value);
    }
  }
  collectBindings(root);
  const found = new Set();
  function visit(node, parent = null, parentKey = '') {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'Identifier') {
      const isKey = parent && ((parent.type === 'MemberExpression' && parentKey === 'property' && !parent.computed)
        || (parent.type === 'Property' && parentKey === 'key' && !parent.computed && !parent.shorthand)
        || (parent.type === 'MethodDefinition' && parentKey === 'key' && !parent.computed)
        || ((parent.type === 'VariableDeclarator' || /Function(?:Declaration|Expression)$/.test(parent.type)
          || parent.type === 'ArrowFunctionExpression' || parent.type === 'CatchClause') && parentKey !== 'init' && parentKey !== 'body'));
      if (!isKey && !bindings.has(node.name) && definitions[node.name]) found.add(node.name);
      return;
    }
    for (const [key, value] of Object.entries(node)) {
      if (key === 'start' || key === 'end') continue;
      if (Array.isArray(value)) value.forEach(child => visit(child, node, key));
      else if (value && typeof value === 'object') visit(value, node, key);
    }
  }
  visit(root);
  return found;
}
function definitionNode(name) {
  const parsed = acorn.parse(definitions[name], {ecmaVersion: 'latest'}).body[0];
  if (parsed.type === 'FunctionDeclaration') return parsed;
  return parsed.expression?.right || parsed.declarations?.[0]?.init || parsed.expression;
}
const loaded = new Set(['$', 'tX']);
const loading = new Set();
function load(name) {
  if (loaded.has(name) || loading.has(name)) return;
  if (!definitions[name]) throw new Error(`Missing Hito grammar dependency: ${name}`);
  loading.add(name);
  for (const dependency of dependenciesFrom(definitionNode(name))) load(dependency);
  const source = definitions[name];
  debug(`Loading grammar dependency ${name}`);
  vm.runInContext(source.startsWith('function ') ? source : `var ${source};`, context, {timeout: 2000});
  loading.delete(name);
  loaded.add(name);
}
for (const dependency of dependenciesFrom(englishNode)) load(dependency);
load(hanziNode.name);
load('n9');
load('r2');
load('sk');
const bilingualName = Object.keys(definitions).find(name => {
  const source = definitions[name];
  return source.includes(`Object.entries(${languageRootName})`) && source.includes('.settings.known')
    && source.includes('.settings.annotation');
});
if (!bilingualName) throw new Error('Unsupported Hito bilingual composer');
load(bilingualName);
const bilingualGrammar = context[bilingualName];
const inflector = Object.values(context).find(value => typeof value?.singular === 'function');
if (!inflector) throw new Error('Unsupported Hito word inflector');
debug('Loaded grammar');
const tables = [];
const tokenizer = acorn.tokenizer(bundle, {ecmaVersion: 'latest'});
for (;;) {
  const token = tokenizer.getToken();
  if (token.type.label === 'eof') break;
  if (token.type.label === 'string' && token.value.startsWith('key,')) tables.push(token.value);
}
context.vocabularyCsv = tables[1];
context.phrasesCsv = tables[2];
context.storyCsv = tables[3];
vm.runInContext('var l=r2(vocabularyCsv,true),u=r2(phrasesCsv,true),story=r2(storyCsv,false);', context, {timeout: 1000});
debug('Loaded dictionaries');
function clean(value) { return String(value || '').replace(/<[^>]+>/g, '').replace(/_/g, ' ').replace(/#/g, '').trim(); }
function plain(value, part) {
  return clean(value.replace(/\[([^\[\]]*%[^\[\]]*)\]/g, (_, text) => text.split('%')[part] || ''));
}
function entity() { return {settings:{language:'hanzi', known:'english', annotation:'pinyin'}, action:{}}; }
function compose(method, args) {
  return bilingualGrammar.hanzi[method](entity(), ...args);
}
function constant(n) {
  if (n.type === 'Literal') return n.value;
  if (n.type === 'UnaryExpression') {
    const value = constant(n.argument);
    if (n.operator === '!') return !value;
    if (n.operator === '-') return -value;
    if (n.operator === '+') return +value;
  }
  if (n.type === 'TemplateLiteral' && !n.expressions.length) return n.quasis[0].value.cooked;
  if (n.type === 'ArrayExpression') return n.elements.map(constant);
  if (n.type === 'ObjectExpression') return Object.fromEntries(n.properties.map(p => {
    if (p.type !== 'Property' || p.computed) throw new Error('dynamic');
    return [p.key.name || p.key.value, constant(p.value)];
  }));
  throw new Error('dynamic');
}
const calls = [];
function walk(n) {
  if (!n || typeof n !== 'object') return;
  if (n.type === 'CallExpression' && n.callee.type === 'MemberExpression') {
    const method = n.callee.property.name || n.callee.property.value;
    if (/^compose.*Message$/.test(method)) calls.push({method, nodes:n.arguments.slice(1)});
  }
  for (const v of Object.values(n)) {
    if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === 'object') walk(v);
  }
}
walk(tree);
debug('Indexed call sites');
const records = new Map();
function family(value) {
  return clean(value).toLowerCase().replace(/\b(?:a|an|some|one|two|three|four|five|six|seven|eight|nine|ten)\b|\d+(?:\.\d+)?/g,'quantity')
    .replace(/[a-z]+/g, word => inflector.singular(word));
}
function add(output, identity) {
  const chinese = plain(output, 0), english = plain(output, 3);
  if (!/[\u3400-\u9fff]/.test(chinese) || !english || /undefined|\{[^}]*\}/.test(chinese + english)) return;
  const key = chinese + '\n' + english;
  records.set(key, {chinese, english, identity: family(identity || english)});
}
// Full story rows matter: a displayed message may contain several commands.
const story = context.story;
function storyRows(value) {
  for (const child of Object.values(value || {})) {
    if (typeof child === 'string') {
      context.command = child; context.entity = entity();
      try { add(vm.runInContext('sk(entity,command,false)', context, {timeout:30})); } catch {}
      for (const command of child.matchAll(/\{[^{}]+\}/g)) {
        context.command = command[0]; context.entity = entity();
        try { add(vm.runInContext('sk(entity,command,false)', context, {timeout:30})); } catch {}
      }
    } else storyRows(child);
  }
}
if (!cachedCatalog) storyRows(story);
else cachedCatalog.records.forEach(row => add(`[${row.chinese}%%%${row.english}]`, clean(row.identity)));
debug('Expanded authored dialogue');
const phrases = vm.runInContext('u.hanzi', context);
const englishPhrases = vm.runInContext('u.english', context);
for (const [group, values] of Object.entries(phrases)) {
  for (const [key, chinese] of Object.entries(values)) {
    const english = englishPhrases[group]?.[key];
    if (typeof chinese === 'string' && english && !/\{/.test(chinese)) add(`[${chinese}%%%${english}]`);
  }
}
function canonicalArgs(args) {
  return args.map((value, i) => typeof value === 'number' &&
    (args[i+1] === 'counter' || (i === 1 && args.length <= 4)) ? 2 : value);
}
for (const call of cachedCatalog ? [] : calls) {
  try {
    const args = call.nodes.map(constant);
    add(compose(call.method, args), plain(compose(call.method, canonicalArgs(args)), 3));
  } catch {}
}
debug('Expanded fixed calls');
const vocabulary = [];
for (const [group, values] of Object.entries(context.l.hanzi)) {
  for (const [key, chinese] of Object.entries(values)) {
    if (typeof chinese !== 'string' || !chinese) continue;
    const english = context.l.english[group]?.[key];
    if (typeof english === 'string') vocabulary.push({key, group, chinese:clean(chinese),
      english:clean(english), pinyin:clean(context.l.pinyin[group]?.[key])});
  }
}
console.log(JSON.stringify({records:[...records.values()], vocabulary,
  archive_hash:archiveHash, extractor_version:extractorVersion, calls:calls.length}));

function normalize(s) { return clean(s).toLowerCase().replace(/[^\p{L}\p{N}]/gu, ''); }
function oneEdit(a,b) {
  if (Math.abs(a.length-b.length)>1) return false;
  let i=0,j=0,edits=0;
  while(i<a.length && j<b.length) {
    if(a[i]===b[j]) { i++; j++; continue; }
    if(++edits>1) return false;
    if(a.length>=b.length) i++;
    if(b.length>=a.length) j++;
  }
  return edits+(a.length-i)+(b.length-j)<=1;
}
const roleNames = new Set(['topic','subject','object','target','targetObject','targetDirection',
  'context','contextWith','togetherWith','source','sourceOff','time','counter','possessive',
  'possessiveOf','possessiveFor','possessiveObject','progressive','purposeFor','connection']);
function resolve(text) {
  const normalized = normalize(text);
  const english = !/[\u3400-\u9fff]/.test(text);
  let seen = vocabulary.filter(v => {
    const word = normalize(english ? v.english : v.chinese);
    return word && (english ? new RegExp(`\\b${v.english.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}\\b`, 'i').test(text)
      : normalized.includes(word));
  });
  if (!english) {
    const objectSpans = seen.filter(v => v.group === 'objects').flatMap(v =>
      [...normalized.matchAll(new RegExp(normalize(v.chinese),'g'))].map(m => ({start:m.index,end:m.index+normalize(v.chinese).length})));
    seen = seen.filter(v => {
      const word = normalize(v.chinese);
      return [...normalized.matchAll(new RegExp(word,'g'))].some(m =>
        !objectSpans.some(span => span.start <= m.index && span.end >= m.index+word.length && span.end-span.start > word.length));
    });
  }
  const verbs = [...new Set(seen.filter(v => v.group === 'verbs').map(v => v.key))];
  const nouns = [...new Set(seen.filter(v => ['objects','pronouns'].includes(v.group)).map(v => v.key))];
  const objects = [...new Set(seen.filter(v => v.group === 'objects').map(v => v.key))];
  const modifiers = [...new Set(seen.filter(v => ['objects','adjectives','adverbs'].includes(v.group)).map(v => v.key))];
  const numbers = [...new Set((text.match(/\d+(?:\.\d+)?/g) || []).map(Number))];
  const result = new Map();
  const signatures = new Set();
  let attempts = 0;
  const started = Date.now();
  for (const call of calls) {
    if (['composeSimpleMessage','composeCustomMessage','composeInfoListMessage','composeNegativeListMessage'].includes(call.method)) continue;
    if (!english) {
      if (/Progressive/.test(call.method) && !/正在/.test(normalized)) continue;
      if (/Necessitative/.test(call.method) && !/得|必须|须/.test(normalized)) continue;
      if (/PotentialNegative|Failure/.test(call.method) && !/不能|不会|无法|不可以/.test(normalized)) continue;
      if (/Negative/.test(call.method) && !/没|不/.test(normalized)) continue;
      if (/Question/.test(call.method) && !/[?？]|吗|什么|哪里|谁|怎么|哪/.test(text)) continue;
      if (/Desiderative/.test(call.method) && !/想/.test(normalized)) continue;
      if (/Prescriptive/.test(call.method) && !/应该/.test(normalized)) continue;
    }
    const values = call.nodes.map(n => { try { return {fixed:true, value:constant(n)}; } catch { return {fixed:false}; } });
    if (values[0]?.fixed && typeof values[0].value === 'string' && !verbs.includes(values[0].value)) continue;
    const domains = call.nodes.map((node, i) => {
      if (values[i].fixed) return [values[i].value];
      const next = values[i+1]?.value;
      const code = bundle.slice(node.start,node.end);
      if (i === 0) return verbs;
      if (next === 'counter') return numbers;
      if (node.type === 'UnaryExpression' && node.operator === '!') return [false,true];
      if (node.type === 'ObjectExpression' || i >= 13) return [{}];
      if (node.type === 'ArrayExpression' || /\.map\(/.test(code)) return [];
      if (/\.name|\.adjective/.test(code)) return [null,...modifiers.slice(0,8)];
      if (/\.type|\.object/.test(code) && roleNames.has(next)) return objects.slice(0,8);
      if (roleNames.has(next)) return [null,...nouns.slice(0,8)];
      if (i > 0 && typeof values[i-1]?.value === 'string' && roleNames.has(values[i-1].value)) return [false,true];
      if (/\.verb|\.equip|\.unequip|\.dismount|\.mount|triggers\[/.test(code)) return verbs;
      if (/\.cost|\.quantity|\.amount|\.counter/.test(code)) return numbers;
      const roles = /PotentialNegative/.test(call.method) ? [2,5,8] : /Question/.test(call.method) ? [2,4,7,10] : [2,5,8,11];
      if (roles.includes(i)) return ['object','subject','target','source','time','context','togetherWith','targetDirection'];
      return [null,...nouns.slice(0,8)];
    });
    if (domains.some(d => !d.length)) continue;
    const signature = JSON.stringify([call.method,domains]);
    if (signatures.has(signature)) continue;
    signatures.add(signature);
    const count = domains.reduce((a,d) => a*d.length,1);
    if (count > 800) continue;
    function build(i,args) {
      if (attempts >= 1800 || Date.now()-started > 1500) return;
      if (i < domains.length) { for (const v of domains[i]) build(i+1,args.concat([v])); return; }
      attempts++;
      try {
        const output = compose(call.method,args);
        const chinese = plain(output,0), englishText = plain(output,3);
        const target = normalize(english ? englishText : chinese);
        // Strict lexical coverage keeps unrelated grammar candidates out of fuzzy matching.
        if (!target || !oneEdit(target,normalized) || /undefined/.test(output)) return;
        const identity = family(plain(compose(call.method,canonicalArgs(args)),3));
        result.set(chinese+'\n'+englishText,{chinese,english:englishText,identity});
      } catch {}
    }
    build(0,[]);
  }
  return [...result.values()];
}
readline.createInterface({input:process.stdin}).on('line', line => {
  context.resolve = resolve;
  context.input = JSON.parse(line).text;
  try { console.log(JSON.stringify({records:vm.runInContext('resolve(input)',context,{timeout:2000})})); }
  catch (error) { console.log(JSON.stringify({error:error.message,records:[]})); }
});
