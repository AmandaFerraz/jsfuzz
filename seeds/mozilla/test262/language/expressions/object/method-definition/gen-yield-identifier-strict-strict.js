// |reftest| error:SyntaxError
'use strict';
// This file was procedurally generated from the following sources:
// - src/generators/yield-identifier-strict.case
// - src/generators/default/obj-method.template
/*---
description: It's an early error if the generator body has another function body with yield as an identifier in strict mode. (Generator method)
esid: prod-GeneratorMethod
features: [generators]
flags: [generated, onlyStrict]
negative:
  phase: parse
  type: SyntaxError
info: |
    14.4 Generator Function Definitions

    GeneratorMethod[Yield, Await]:
      * PropertyName[?Yield, ?Await] ( UniqueFormalParameters[+Yield, ~Await] ) { GeneratorBody }

---*/
throw "Test262: This statement should not be evaluated.";

var callCount = 0;

var gen = {
  *method() {
    callCount += 1;
    (function() {
        var yield;
        throw new Test262Error();
      }())
  }
}.method;

var iter = gen();



assert.sameValue(callCount, 1);
