import './home-page.css';
import { WorkspaceHeader } from '@/components/app-shell/workspace-header';
import { ProfileAvatar } from '@/components/profile-avatar';
import { useProfiles } from '@/hooks/use-profiles';
import { useEngines } from '@/hooks/use-engines';
import { setCloneSetting, useCloneSetting } from '@/lib/store/clone-settings';
import { blankLongformDraft, editLongform } from '@/features/longform/longform-session';
import { projectLibrary, type LongformProject } from '@/features/longform/project-library';
import { openDubProject } from '@/features/dub/dub-session';
import type { DubProject } from '@/features/projects/project-format';
import { Link, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { apiJson } from '@/lib/api/client';
import { runRendererTask } from '@/lib/global-error-recovery';
import { ArrowRightIcon, AudioLinesIcon, BookOpenIcon, FilmIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Home is a start line, not a feature catalogue: the script box leads (it is
 * the same text the voice studio edits) and the user's recent work follows.
 * Destinations and saved voices live in the sidebar only, never twice.
 */
export function HomePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const text = useCloneSetting('text');
  const selectedProfileId = useCloneSetting('selectedProfileId');
  const language = useCloneSetting('language');
  const { activeTts } = useEngines();
  const { data: profiles = [] } = useProfiles();
  const { data: dubProjects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: ({ signal }) => apiJson<DubProject[]>('/projects', { signal }),
  });
  const { data: longformProjects = [] } = useQuery({
    queryKey: ['longform-projects'],
    queryFn: projectLibrary.list,
  });
  const selectedProfile = profiles.find((profile) => profile.id === selectedProfileId);
  const recentProjects = [
    ...dubProjects.map((project) => ({
      kind: 'dub' as const,
      project,
      updatedAt:
        (project.updated_at || 0) < 1e12
          ? (project.updated_at || 0) * 1000
          : project.updated_at || 0,
    })),
    ...longformProjects.map((project) => ({
      kind: 'longform' as const,
      project,
      updatedAt: project.updatedAt,
    })),
  ]
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, 5);
  const openProject = async (
    item: { kind: 'dub'; project: DubProject } | { kind: 'longform'; project: LongformProject },
  ) => {
    if (item.kind === 'dub') {
      const project = await apiJson<DubProject>('/projects/' + encodeURIComponent(item.project.id));
      if (openDubProject(project)) await navigate({ to: '/dub' });
      return;
    }
    editLongform(item.project.mode, {
      ...blankLongformDraft(),
      ...structuredClone(item.project.draft),
      projectId: item.project.id,
    });
    await navigate({
      to: item.project.mode === 'stories' ? '/stories' : '/audiobook',
    });
  };
  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkspaceHeader>
        <h1 className="text-sm font-medium">{t('nav.home')}</h1>
      </WorkspaceHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="home-content">
          <section aria-labelledby="home-title" className="home-start">
            <h2 id="home-title" className="home-title">
              {t('homeUi.title')}
            </h2>
            <p className="home-lede">{t('homeUi.subtitle')}</p>
            <form
              className="home-composer"
              onSubmit={(event) => {
                event.preventDefault();
                runRendererTask('Home script to voice studio', () => navigate({ to: '/clone' }));
              }}
            >
              <label htmlFor="home-script" className="sr-only">
                {t('homeUi.scriptLabel')}
              </label>
              <textarea
                id="home-script"
                value={text}
                rows={4}
                spellCheck={false}
                placeholder={t('homeUi.scriptPlaceholder')}
                onChange={(event) => setCloneSetting('text', event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div className="home-composer-bar">
                <Link to="/personas" className="home-voice-chip">
                  {selectedProfile ? (
                    <ProfileAvatar
                      name={selectedProfile.name}
                      imageUrl={selectedProfile.image_url}
                      className="size-5 text-[10px]"
                    />
                  ) : (
                    <span aria-hidden="true" className="home-voice-dot" />
                  )}
                  <span className="truncate">
                    {selectedProfile ? selectedProfile.name : t('homeUi.chooseVoice')}
                  </span>
                </Link>
                <span className="home-meta">
                  {language === 'Auto' ? t('clone.auto') : language}
                  {activeTts && (
                    <>
                      <span aria-hidden="true"> · </span>
                      {activeTts.display_name.replace(/\s*\(.*\)$/, '')}
                    </>
                  )}
                </span>
                <span className="home-count">{t('clone.characters', { count: text.length })}</span>
                <button type="submit" className="home-go">
                  {t('homeUi.continue')}
                  <ArrowRightIcon aria-hidden="true" className="size-4" />
                </button>
              </div>
            </form>
          </section>

          <section aria-labelledby="home-recent" className="home-recent">
            <div className="home-list-head">
              <h2 id="home-recent">{t('homeUi.recent')}</h2>
              {recentProjects.length > 0 && <Link to="/projects">{t('projects.all')}</Link>}
            </div>
            {recentProjects.length > 0 ? (
              <ul className="home-list">
                {recentProjects.map((item) => {
                  const Icon =
                    item.kind === 'dub'
                      ? FilmIcon
                      : item.project.mode === 'stories'
                        ? AudioLinesIcon
                        : BookOpenIcon;
                  const label =
                    item.kind === 'dub'
                      ? t('dubWorkspace.title')
                      : t(item.project.mode === 'stories' ? 'nav.stories' : 'audiobook.title');
                  return (
                    <li key={item.kind + ':' + item.project.id}>
                      <button
                        type="button"
                        className="home-row"
                        onClick={() => void openProject(item)}
                      >
                        <Icon aria-hidden="true" className="home-row-icon" />
                        <span className="home-row-name">{item.project.name}</span>
                        <span className="home-row-meta">{label}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="home-empty">
                {t('homeUi.noProjects')} <Link to="/dub">{t('dubWorkspace.title')}</Link>
                {' · '}
                <Link to="/audiobook">{t('audiobook.title')}</Link>
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
