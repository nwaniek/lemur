import puppeteer from "puppeteer-core"; import { pathToFileURL } from "node:url";
const [f,o,h,w]=[process.argv[2],process.argv[3],process.argv[4],+(process.argv[5]||1400)];
const b=await puppeteer.launch({executablePath:"/usr/bin/google-chrome-stable",headless:true,args:["--no-sandbox","--disable-setuid-sandbox"]});
const p=await b.newPage(); const e=[]; p.on("pageerror",x=>e.push(String(x)));
await p.setViewport({width:1600,height:900}); await p.goto(pathToFileURL(f).href,{waitUntil:"networkidle0"});
await p.evaluate(h2=>{location.hash=h2;},h); await new Promise(r=>setTimeout(r,w));
await p.screenshot({path:o}); await b.close(); if(e.length)console.log("ERR",e[0]); console.log("wrote",o);
