import { useSyncExternalStore, type ComponentProps } from 'react';
import { BorderBeam } from 'border-beam';
import { VoiceBeam } from 'voice-glow';
import { ThinkingOrb } from 'thinking-orbs';
import { MetalFx } from 'metal-fx';
import { BotAvatar } from 'bot-avatars';
import { ImageGeneration } from 'img-fx';
export { Liquid } from 'liquid-gooey';

/* Sado's motion effects come from the libraries.dev set (MIT, all local): a
   border beam on whatever is working, a voice glow that rises with the
   microphone, thinking orbs for waits, liquid metal on the few emphasised
   buttons, a living bot avatar for the agent, the gooey liquid that slides
   between segments, and the pixel loader while images are fetched. These wrappers
   only feed them the app's resolved light/dark theme (the `dark` class on
   <html>, which also follows the OS when the theme is "system"); colours and
   timing stay the libraries' own defaults, as on libraries.dev. Each library
   honours prefers-reduced-motion itself. */

function subscribe(notify: () => void) {
  const observer = new MutationObserver(notify);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  return () => observer.disconnect();
}
const isDark = () => document.documentElement.classList.contains('dark');

export function useColorScheme(): 'dark' | 'light' {
  return useSyncExternalStore(subscribe, isDark, () => true) ? 'dark' : 'light';
}

export function Beam(props: Omit<ComponentProps<typeof BorderBeam>, 'theme'>) {
  return <BorderBeam theme={useColorScheme()} {...props} />;
}

export function VoiceGlow(props: Omit<ComponentProps<typeof VoiceBeam>, 'theme'>) {
  return <VoiceBeam theme={useColorScheme()} {...props} />;
}

/** `theme` may pin the dot colour when the orb sits on a fixed surface (an indigo button). */
export function Orb(props: ComponentProps<typeof ThinkingOrb>) {
  const scheme = useColorScheme();
  return <ThinkingOrb {...props} theme={props.theme ?? scheme} />;
}

export function Metal(props: Omit<ComponentProps<typeof MetalFx>, 'theme'>) {
  return <MetalFx theme={useColorScheme()} {...props} />;
}

export function Avatar(props: ComponentProps<typeof BotAvatar>) {
  return <BotAvatar {...props} />;
}

export function ImageLoader(props: Omit<ComponentProps<typeof ImageGeneration>, 'theme'>) {
  return <ImageGeneration theme={useColorScheme()} {...props} />;
}

/** The app-wide busy indicator: a small working orb where a spinning loader
    used to be. It takes the loader's size classes (default 1rem). */
export function LoadingOrb({
  className,
  ...props
}: Omit<ComponentProps<typeof ThinkingOrb>, 'size' | 'state'>) {
  return (
    <Orb
      state="composing"
      size={20}
      data-slot="loading-orb"
      className={['inline-block size-4 shrink-0', className].filter(Boolean).join(' ')}
      {...props}
    />
  );
}
