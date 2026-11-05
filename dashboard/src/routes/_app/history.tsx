import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import type { FormEvent } from "react";

import { PageHeader, Panel } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { STATUS_LABELS, formatDateTime, formatNumber, sourceLabel } from "@/lib/format";
import { historySchema } from "@/lib/schemas";
import { getHistoryFn } from "@/server/fns";

export const Route = createFileRoute("/_app/history")({
  validateSearch: historySchema,
  loaderDeps: ({ search }) => search,
  loader: ({ deps }) => getHistoryFn({ data: deps }),
  head: () => ({ meta: [{ title: "History - Prins" }] }),
  component: HistoryPage,
});

const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "printed", label: "Printed" },
  { value: "dismissed", label: "Dismissed" },
  { value: "ignored", label: "Filtered" },
] as const;

function HistoryPage() {
  const { rows, total, pageSize, sources } = Route.useLoaderData();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = String(new FormData(event.currentTarget).get("q") ?? "");
    void navigate({ search: (previous) => ({ ...previous, search: text, page: 1 }) });
  };

  return (
    <>
      <PageHeader title="History" description={`${formatNumber(total)} decided messages`} />

      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <nav className="flex gap-1 overflow-x-auto" aria-label="Filter by outcome">
          {STATUS_FILTERS.map((filter) => (
            <Link
              key={filter.value}
              from={Route.fullPath}
              search={(previous) => ({ ...previous, status: filter.value, page: 1 })}
              className={`shrink-0 rounded-md px-2.5 py-1 text-sm ${
                search.status === filter.value
                  ? "bg-secondary font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {filter.label}
            </Link>
          ))}
        </nav>
        <div className="flex gap-2">
          <select
            aria-label="Filter by source"
            className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm"
            value={search.source}
            onChange={(event) =>
              void navigate({
                search: (previous) => ({ ...previous, source: event.target.value, page: 1 }),
              })
            }
          >
            <option value="all">All sources</option>
            {sources.map((source) => (
              <option key={source} value={source}>
                {sourceLabel(source)}
              </option>
            ))}
          </select>
          <form onSubmit={onSearch} className="relative min-w-0 flex-1 md:w-56 md:flex-none">
            <Search
              className="absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              name="q"
              defaultValue={search.search}
              placeholder="Search"
              aria-label="Search notes"
              className="pl-7"
            />
          </form>
        </div>
      </div>

      <Panel className="!p-0">
        {rows.length === 0 ? (
          <p className="p-5 text-sm text-muted-foreground">Nothing matches these filters.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Note</TableHead>
                <TableHead className="hidden sm:table-cell">From</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead className="hidden pr-4 text-right md:table-cell">Received</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="max-w-48 pl-4 whitespace-normal sm:max-w-md">
                    <p className="font-medium">{row.title}</p>
                    <p className="text-xs text-muted-foreground sm:hidden">
                      {sourceLabel(row.source)}
                      {row.sender ? ` - ${row.sender}` : ""}
                    </p>
                    {row.engine === "fallback" ? (
                      <p className="text-xs text-muted-foreground">Written without the model</p>
                    ) : null}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground sm:table-cell">
                    {sourceLabel(row.source)}
                    {row.sender ? ` - ${row.sender}` : ""}
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.status === "printed" ? "default" : "outline"}>
                      {STATUS_LABELS[row.status]}
                    </Badge>
                  </TableCell>
                  <TableCell className="hidden pr-4 text-right text-muted-foreground tabular-nums md:table-cell">
                    {formatDateTime(row.createdAt)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>

      {lastPage > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={search.page <= 1}
            onClick={() =>
              void navigate({ search: (previous) => ({ ...previous, page: search.page - 1 }) })
            }
          >
            Previous
          </Button>
          <span className="text-muted-foreground tabular-nums">
            Page {search.page} of {lastPage}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={search.page >= lastPage}
            onClick={() =>
              void navigate({ search: (previous) => ({ ...previous, page: search.page + 1 }) })
            }
          >
            Next
          </Button>
        </div>
      ) : null}
    </>
  );
}
