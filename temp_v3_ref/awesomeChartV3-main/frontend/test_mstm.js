const { Calculator } = require("./dist_test/Calculator.js");
const { defaultMSTMOptions } = require("./dist_test/types.js");

const data = [];
let time = 1000;
let price = 100;
// Generate an obvious downtrend then uptrend to trigger MSS
for(let i=0; i<30; i++) {
  data.push({
    time: time++,
    open: price,
    high: price + 1,
    low: price - 2,
    close: price - 1
  });
  price -= 1;
}

// generate an UP pivot
price += 2;
for(let i=0; i<5; i++) {
  data.push({
    time: time++,
    open: price,
    high: price + 2,
    low: price - 1,
    close: price + 1
  });
  price += 1;
}

price -= 2;
for(let i=0; i<10; i++) {
  data.push({
    time: time++,
    open: price,
    high: price + 1,
    low: price - 2,
    close: price - 1
  });
  price -= 1;
}

// Uptrend break
price += 2;
for(let i=0; i<30; i++) {
  data.push({
    time: time++,
    open: price,
    high: price + 20, // push it very high to break MSS
    low: price - 1,
    close: price + 20
  });
  price += 1;
}

const targets = Calculator.computeTargets(data, defaultMSTMOptions);
console.log("Found targets:", targets.length);
for (const t of targets) {
    console.log(t);
}
