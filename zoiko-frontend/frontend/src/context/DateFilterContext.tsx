import { createContext, useContext } from "react";
import type { DateRange } from "@/components/DateFilter";

export const DateFilterContext = createContext<DateRange | null>(null);

export function useDateFilter(): DateRange | null {
  return useContext(DateFilterContext);
}
