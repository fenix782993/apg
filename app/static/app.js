const screens = ["home","discounts","partners","car","profile"];
function show(id){
  screens.forEach(x=>document.getElementById(x).classList.toggle("active",x===id));
  document.querySelectorAll(".nav button").forEach((b,i)=>b.classList.toggle("active",screens[i]===id));
  window.scrollTo({top:0,behavior:"smooth"});
}
async function openQR(discount){
  document.getElementById("discountBig").textContent = discount+"%";
  const img=document.getElementById("qr");
  img.src="/static/placeholder.svg";
  document.getElementById("qrModal").classList.add("show");
  try{
    const r=await fetch("/api/qr",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({discount,user_id:"APG-184729"})});
    const blob=await r.blob();
    img.src=URL.createObjectURL(blob);
  }catch(e){}
}
function closeQR(){document.getElementById("qrModal").classList.remove("show")}
async function loadDeals(){
  try{
    const r=await fetch("/api/discounts"); const data=await r.json();
    const html=data.map(x=>`<article class="deal"><div><div class="off">-${x.discount}%</div><b>${x.partner}</b><small>${x.title} · ${x.distance}</small></div><button onclick="openQR(${x.discount})">Получить скидку</button></article>`).join("");
    document.getElementById("discountCards").innerHTML=html;
    document.getElementById("homeCards").innerHTML=data.slice(0,4).map(x=>`<article class="deal"><div><div class="off">-${x.discount}%</div><b>${x.partner}</b><small>${x.category}</small></div><button onclick="openQR(${x.discount})">Получить</button></article>`).join("");
  }catch(e){console.log(e)}
}
loadDeals();
