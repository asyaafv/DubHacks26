import { useEffect, useRef, useState } from 'react';
import { searchRewards, searchSuggestions } from '../api/client';
import type { SearchChip, SearchHit } from '../types';

const DEBOUNCE_MS = 250;

export interface SearchState {
  query: string;
  setQuery: (value: string) => void;
  /** null = nothing searched yet; [] = searched, no matches. */
  results: SearchHit[] | null;
  chips: SearchChip[];
  loading: boolean;
  error: string | null;
}

export function useSearch(): SearchState {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchHit[] | null>(null);
  const [chips, setChips] = useState<SearchChip[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    searchSuggestions()
      .then((suggestions) => {
        if (!cancelled) setChips(suggestions.chips);
      })
      .catch(() => {
        // Chips are an enhancement; search still works without them.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      requestSeq.current += 1;
      setResults(null);
      setError(null);
      setLoading(false);
      return;
    }
    const id = (requestSeq.current += 1);
    setLoading(true);
    const timer = window.setTimeout(() => {
      searchRewards(trimmed)
        .then((response) => {
          if (requestSeq.current !== id) return;
          setResults(response.results);
          setError(null);
        })
        .catch((cause: unknown) => {
          if (requestSeq.current !== id) return;
          setResults([]);
          setError(cause instanceof Error ? cause.message : 'Search failed');
        })
        .finally(() => {
          if (requestSeq.current === id) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  return { query, setQuery, results, chips, loading, error };
}
