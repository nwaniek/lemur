import puppeteer from "puppeteer-core"; import { pathToFileURL } from "node:url";
const [f,o,w]=[process.argv[2],process.argv[3],+(process.argv[4]||2000)];
const b=await puppeteer.launch({executablePath:"/usr/bin/google-chrome-stable",headless:true,args:["--no-sandbox","--disable-setuid-sandbox"]});
const p=await b.newPage(); await p.setViewport({width:1600,height:900});
await p.goto(pathToFileURL(f).href,{waitUntil:"networkidle0"});
await p.evaluate(()=>{location.hash="#/1/1";}); await new Promise(r=>setTimeout(r,400));
await p.keyboard.press("ArrowRight"); await new Promise(r=>setTimeout(r,w));
await p.screenshot({path:o}); await b.close(); console.log("wrote",o);
