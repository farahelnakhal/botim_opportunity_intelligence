import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollIntoView (used by Chat.tsx to autoscroll).
// Guarded because this setup file also loads for node-environment test files
// (e.g. darkModeContrast.test.ts) where `Element` doesn't exist at all.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
