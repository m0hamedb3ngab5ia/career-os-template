import "@testing-library/jest-dom/vitest";
import { setAppLocale } from "../lib/format";

// Formatting must not depend on the machine running the tests (LC_ALL, OS language).
setAppLocale("en-US");
