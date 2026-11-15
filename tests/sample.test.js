import { describe, expect, it } from "vitest";
import { TestDriver } from "testdriverai/vitest/hooks";

describe("TodoMVC Sample App Test", () => {
  it("should create todo items and complete one", async (context) => {
    const testdriver = TestDriver(context);

    await testdriver.provision.chrome({
      url: "https://todomvc.com/examples/react/dist/",
    });

    const input = await testdriver.find('the "What needs to be done?" input field');
    await input.click();
    await testdriver.type("Write TestDriver tests");
    await testdriver.pressKeys(["enter"]);

    await testdriver.type("Run tests in CI");
    await testdriver.pressKeys(["enter"]);

    const checkbox = await testdriver.find(
      'the round toggle checkbox next to "Write TestDriver tests"'
    );
    await checkbox.click();

    const assertResult = await testdriver.assert(
      '"Write TestDriver tests" is completed with a checkmark and the footer shows "1 item left!"'
    );
    expect(assertResult).toBeTruthy();
  });
});
