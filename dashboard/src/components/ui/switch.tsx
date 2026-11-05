import { Switch as SwitchPrimitive } from "@base-ui/react/switch";

export function Switch(props: SwitchPrimitive.Root.Props) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className="relative inline-flex h-6 w-10 shrink-0 cursor-pointer rounded-full bg-input transition-colors data-[checked]:bg-primary"
      {...props}
    >
      <SwitchPrimitive.Thumb className="absolute top-0.5 left-0.5 size-5 rounded-full bg-background shadow-sm transition-transform duration-200 ease-out data-[checked]:translate-x-4" />
    </SwitchPrimitive.Root>
  );
}
