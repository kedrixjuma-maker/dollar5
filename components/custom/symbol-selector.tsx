'use client';

import { useMemo } from 'react';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { ActiveSymbol } from '@deriv/core';
import { getSubmarketDisplayName } from '@/lib/active-symbols-display-names';

interface SymbolSelectorProps {
  symbols: ActiveSymbol[];
  activeSymbol: ActiveSymbol | null;
  onSymbolChange: (symbol: string) => void;
}

type SubmarketGroup = { displayName: string; symbols: ActiveSymbol[] };

function groupBySubmarket(symbols: ActiveSymbol[]): Map<string, SubmarketGroup> {
  const groups = new Map<string, SubmarketGroup>();
  for (const symbol of symbols) {
    const key = symbol.submarket;
    const existing = groups.get(key);
    if (existing) {
      existing.symbols.push(symbol);
    } else {
      const displayName =
        symbol.submarket_display_name ?? getSubmarketDisplayName(symbol.submarket);
      groups.set(key, { displayName, symbols: [symbol] });
    }
  }
  return groups;
}

export function SymbolSelector({
  symbols,
  activeSymbol,
  onSymbolChange,
}: SymbolSelectorProps) {
  const grouped = useMemo(() => groupBySubmarket(symbols), [symbols]);

  return (
    <Select
      value={activeSymbol?.underlying_symbol ?? ''}
      onValueChange={onSymbolChange}
    >
      <SelectTrigger className="w-full">
        <SelectValue placeholder="Select a symbol" />
      </SelectTrigger>
      <SelectContent>
        {Array.from(grouped.entries()).map(([submarket, { displayName, symbols: group }]) => (
          <SelectGroup key={submarket}>
            <SelectLabel>{displayName}</SelectLabel>
            {group.map((symbol) => (
              <SelectItem
                key={symbol.underlying_symbol}
                value={symbol.underlying_symbol}
              >
                {symbol.underlying_symbol_name}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
