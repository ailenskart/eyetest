const http = require('http');

async function test() {
    const fetch = (await import('node-fetch')).default || globalThis.fetch;
    const base = "http://localhost:5000/api/session";
    const sid = "test10";
    
    let res = await fetch(`${base}/start`, { method: 'POST', body: JSON.stringify({session_id: sid}), headers: {'Content-Type': 'application/json'}});
    console.log("start:", (await res.json()).power.right.sph);
    
    res = await fetch(`${base}/${sid}/respond`, { method: 'POST', body: JSON.stringify({intent: "Able to read with pinhole"}), headers: {'Content-Type': 'application/json'}});
    console.log("respond:", (await res.json()).power.right.sph);
    
    res = await fetch(`${base}/${sid}/sync-power`, { method: 'POST', body: JSON.stringify({right: {sph: -1.25}}), headers: {'Content-Type': 'application/json'}});
    console.log("sync-power:", await res.json());
    
    res = await fetch(`${base}/${sid}/status`);
    console.log("after sync:", (await res.json()).current_power.right.sph);
    
    res = await fetch(`${base}/${sid}/respond`, { method: 'POST', body: JSON.stringify({intent: "Blurry"}), headers: {'Content-Type': 'application/json'}});
    console.log("blurry:", (await res.json()).power.right.sph);
}

test().catch(console.error);
