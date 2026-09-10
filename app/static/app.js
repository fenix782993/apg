
const $=s=>document.querySelector(s), api=async(u,o)=>{let r=await fetch(u,o);return r.json()};
let me, view="home";

async function boot(){me=await api("/api/me"); render()}
function nav(v){view=v;render()}
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]))}

function shell(content){
return `<div class="bg"></div><aside>
<div class="brand"><span>APG</span><b>COMMUNITY</b></div>
<div class="profile-mini"><div class="avatar">${esc(me.username[0].toUpperCase())}</div><div><b>${esc(me.username)}</b><small>ID ${me.public_id}</small></div></div>
<nav>
${["home:⌂ Главная","gallery:▦ Галерея","games:◈ Игры","pass:◇ Pass","feed:◉ Лента","leaders:♛ Лидерборд","titles:✦ Титулы","profile:◌ Профиль"].map(x=>{let [id,n]=x.split(":");return `<button class="${view==id?'on':''}" onclick="nav('${id}')">${n}</button>`}).join("")}
</nav><div class="side-foot">SEASON 01<br><b>NIGHT DRIVE</b></div></aside>
<main><header><button class="mobile-menu" onclick="document.querySelector('aside').classList.toggle('open')">☰</button><span>APG / ${view.toUpperCase()}</span><button class="icon" onclick="nav('profile')">◌</button></header>${content}</main>
<div class="bottom">${["home","gallery","games","pass","profile"].map(x=>`<button onclick="nav('${x}')">${({home:"⌂",gallery:"▦",games:"◈",pass:"◇",profile:"◌"})[x]}</button>`).join("")}</div></div>`}

function render(){let c={home:home,gallery:gallery,games:games,pass:pass,feed:feed,leaders:leaders,titles:titles,profile:profile}[view]();$("#app").innerHTML=shell(c)}
function home(){return `<section class="hero"><div><label>APG COMMUNITY · 2026</label><h1>Твоя машина.<br><em>Твой стиль.</em></h1><p>Галерея, игры, Pass, титулы и люди, которые живут автомобилями.</p><button class="grad" onclick="nav('games')">ИГРАТЬ СЕЙЧАС →</button></div><div class="hero-art"><div class="orb"></div><div class="carword">APG<br><span>RIDER</span></div></div></section>
<div class="stats"><div><small>XP</small><b>${me.xp}</b></div><div><small>LEVEL</small><b>${me.level}</b></div><div><small>STREAK</small><b>${me.streak||7} 🔥</b></div><div><small>TITLE</small><b>${esc(me.title)}</b></div></div>
<h2>Сегодня в APG</h2><div class="grid3"><article onclick="nav('gallery')"><i>▦</i><b>Галерея</b><span>Новые кадры сообщества</span></article><article onclick="nav('games')"><i>◈</i><b>Игры</b><span>Зарабатывай XP и поднимайся</span></article><article onclick="nav('pass')"><i>◇</i><b>Free Pass</b><span>50 уровней · сезон Night Drive</span></article></div>`}

async function gallery(){let g=await api("/api/gallery");return `<div class="title-row"><div><label>VISUAL ARCHIVE</label><h2>Галерея</h2></div><button class="grad" onclick="nav('feed')">ДОБАВИТЬ КАДР +</button></div><div class="gallery">${g.map(x=>`<article><img src="${x.image}"><div class="gmeta"><b>${esc(x.title)}</b><span>${esc(x.author)} · ♥ ${x.likes}</span></div></article>`).join("")}</div>`}
async function feed(){let f=await api("/api/feed");return `<div class="title-row"><div><label>SOCIAL</label><h2>Лента</h2></div></div><div class="composer"><textarea id="postText" placeholder="Что нового в твоём гараже?"></textarea><button class="grad" onclick="post()">ОПУБЛИКОВАТЬ</button></div><div class="feed">${f.length?f.map(p=>`<article><div class="posthead"><div class="avatar">${esc((p.username||"?")[0].toUpperCase())}</div><div><b>${esc(p.username)}</b><small>ID ${p.public_id} · ${esc(p.title)}</small></div></div><p>${esc(p.text)}</p><button onclick="like(${p.id})">♥ ${p.likes}</button></article>`).join(""):"<div class='empty'>Пока нет постов. Создай первый.</div>"}</div>`}
async function post(){let t=$("#postText").value.trim();if(!t)return;await api("/api/posts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});render()}
async function like(id){await api("/api/like/"+id,{method:"POST"});render()}

async function games(){return `<label>PLAYGROUND</label><h2>Игры</h2><p class="sub">Каждая игра даёт XP. Результаты попадают в общий рейтинг.</p><div class="games">${[
["quiz","CAR QUIZ","Угадай автомобиль по подсказкам","🏁"],["guess","GUESS CAR","Угадай машину за 10 секунд","🚘"],["reaction","REACTION","Нажми вовремя. Проверь реакцию","⚡"],["battle","CAR BATTLE","Собери билд и победи соперника","⚔️"],["memory","MEMORY","Запомни пары и забери бонус XP","🧠"],["daily","DAILY CHALLENGE","Особое испытание дня","🔥"]].map(g=>`<article onclick="playGame('${g[0]}','${g[1]}')"><span class="gameicon">${g[3]}</span><b>${g[1]}</b><p>${g[2]}</p><strong>PLAY →</strong></article>`).join("")}</div>`}
async function playGame(game,name){let score=Math.floor(Math.random()*400)+100;await api("/api/games/"+game,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({score})});alert(`${name}\n\nРезультат: ${score} XP начислено.`);me=await api("/api/me");render()}

async function pass(){let p=await api("/api/pass");let progress=Math.min(100,(p.xp%1000)/10);return `<label>SEASON 01 · FREE</label><div class="passhero"><div><h2>NIGHT <em>DRIVE</em></h2><p>Сезон для всех. Без оплаты. Играй, выполняй миссии и открывай награды.</p></div><div class="biglevel">${p.level}<small>/ 50</small></div></div><div class="bar"><span style="width:${progress}%"></span></div><div class="rewardgrid">${p.rewards.map(r=>`<article><small>LEVEL ${r.level}</small><b>${r.name}</b><span>${p.level>=r.level?"ОТКРЫТО":"ЗАКРЫТО"}</span></article>`).join("")}</div>`}
async function leaders(){let l=await api("/api/leaderboard");return `<label>GLOBAL RANK</label><h2>Лидерборд</h2><div class="table">${l.map((x,i)=>`<div class="rank ${x.public_id==me.public_id?'self':''}"><strong>#${i+1}</strong><div class="avatar">${x.username[0].toUpperCase()}</div><div><b>${esc(x.username)}</b><small>${esc(x.title)} · ID ${x.public_id}</small></div><strong>${x.xp} XP</strong></div>`).join("")}</div>`}
async function titles(){let t=await api("/api/titles");return `<label>ACHIEVEMENTS</label><h2>Титулы</h2><div class="titles">${t.map(x=>`<article class="${x.rarity}"><span>✦</span><b>${x.name}</b><small>${x.rarity.toUpperCase()}</small><button>ВЫБРАТЬ</button></article>`).join("")}</div>`}
async function profile(){return `<label>MY GARAGE / PROFILE</label><h2>${esc(me.username)}</h2><div class="profile-card"><div class="cover ${me.background}"></div><div class="profile-main"><div class="avatar big">${me.username[0].toUpperCase()}</div><div><h3>${esc(me.username)}</h3><p>ID ${me.public_id}</p><span class="pill">${esc(me.title)}</span></div></div><div class="profile-stats"><b>${me.xp}<small>XP</small></b><b>${me.level}<small>LEVEL</small></b><b>0<small>PHOTOS</small></b><b>${me.streak||7}<small>STREAK</small></b></div></div><h2>Персонализация</h2><div class="grid3"><article><i>◈</i><b>Фон</b><span>Aurora / Night Drive</span></article><article><i>✦</i><b>Рамка</b><span>Открывай в Pass</span></article><article><i>⚡</i><b>Эффект</b><span>Neon / Pulse</span></article></div>`}

boot()
