# Repository Guidelines

## Agentic Workflow Principles

When working on this codebase, follow these core principles for effective AI-assisted development:

### 1. Context-Aware Development
- Always read relevant files before making changes
- Check existing patterns in `apps/web/components/` and `apps/api/app/` 
- Review package.json scripts to understand available commands
- Use `npm run dev` to see live changes across both frontend and backend

### 2. Incremental Implementation
- Make small, testable changes rather than large rewrites
- Run `npm run build --workspace apps/web` after significant frontend changes
- Test API endpoints with `curl http://localhost:8080/health` or visit `/docs`
- Verify changes work before moving to the next step

### 3. Tool Usage Strategy
- File operations: Read existing code before generating new code
- Command execution: Use provided npm scripts (`dev`, `dev:api`, `dev:web`, `db:backup`, `db:reset`, `clean`)
- Search: Look for similar patterns in the codebase before implementing new features
- Error handling: Check logs and stack traces when issues occur

## Project Structure & Module Organization

The project uses a monorepo structure with two main workspaces:
- **Frontend**: Next.js 14 app in `apps/web/` with React components, hooks, and contexts
- **Backend**: FastAPI service in `apps/api/` with Python routes and ORM models
- **Shared Assets**: Static files in `assets/`, user data and SQLite in `data/`
- **Automation**: Helper scripts in `scripts/` for setup, database operations, and cleanup

### Key Directories
```
apps/web/
  ├── components/     # Shared React components
  ├── hooks/          # Custom React hooks
  ├── contexts/       # React context providers
  └── pages/          # Next.js pages

apps/api/
  ├── app/
  │   ├── api/        # FastAPI route definitions
  │   └── models/     # SQLAlchemy ORM models
  └── requirements.txt

scripts/              # Automation helpers
data/                 # SQLite database and backups
assets/               # Static assets
```

## Build, Test, and Development Commands

### Setup and Installation
```bash
npm install           # Install all dependencies (Node.js + Python venv)
npm run ensure:env    # Setup environment variables
npm run ensure:venv   # Create Python virtual environment
```

### Development Workflow
```bash
npm run dev           # Start both API and web servers
npm run dev:api       # Start only the FastAPI backend
npm run dev:web       # Start only the Next.js frontend
```

### Production and Deployment
```bash
npm run build --workspace apps/web    # Compile production bundle
npm run start --workspace apps/web    # Serve production build
```

### Database Operations
```bash
npm run db:backup     # Create timestamped backup in data/backups/
npm run db:reset      # Reset database (WARNING: deletes all data)
```

### Maintenance
```bash
npm run clean         # Remove node_modules, .venv, package-lock.json
```

## Coding Style & Naming Conventions

### Frontend (TypeScript/React)
- **Indentation**: 2 spaces
- **Quotes**: Single quotes for imports and strings
- **Component Naming**: PascalCase for components (`ChatLog.tsx`)
- **Hook Naming**: Prefix with `use` in camelCase (`useThing.ts`)
- **File Location**: Colocate related hooks in `apps/web/hooks/`
- **Tailwind Classes**: Group logically (layout → spacing → typography)
- **Component Style**: Prefer functional components with TypeScript types

Example structure:
```typescript
// apps/web/components/ExampleComponent.tsx
import { useState } from 'react';
import { useCustomHook } from '@/hooks/useCustomHook';

export const ExampleComponent = () => {
  const [state, setState] = useState('');
  
  return (
    <div className="flex flex-col gap-4 p-6">
      {/* Component content */}
    </div>
  );
};
```

### Backend (Python/FastAPI)
- **Indentation**: 4 spaces (PEP 8)
- **Import Order**: Standard library → third-party → local
- **Router Location**: Define routes under `app/api/`
- **Model Updates**: Update `app/models/__init__.py` when adding new ORM models
- **Type Hints**: Use Python type hints for function parameters and return values

Example structure:
```python
# apps/api/app/api/example.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models import Example
from app.database import get_db

router = APIRouter()

@router.get("/examples")
async def get_examples(db: Session = Depends(get_db)):
    return db.query(Example).all()
```

## Testing and Validation

### Current Testing Approach
- **Manual Verification**: Use `npm run build --workspace apps/web` as regression check
- **API Health Check**: `curl http://localhost:8080/health` to verify backend
- **Live Testing**: Use `npm run dev` and test features in browser/Postman

### Future Testing Framework
When adding automated tests:
- **Frontend Tests**: Place Playwright specs in `apps/web/tests/`
  - Naming: `<feature>.spec.ts`
- **Backend Tests**: Place pytest files in `apps/api/tests/`
  - Naming: `test_<module>.py`
- **Test Strategy**: Write tests when fixing bugs to prevent regressions
- **CI Integration**: Add test scripts to package.json before merging

### Pre-Commit Checklist
Before considering work complete:
- [ ] Code builds without errors (`npm run build --workspace apps/web`)
- [ ] API responds to health check (`curl http://localhost:8080/health`)
- [ ] Changes are visible and functional in dev mode (`npm run dev`)
- [ ] No console errors in browser dev tools
- [ ] Python code follows PEP 8 (run linter if available)
- [ ] TypeScript types are correct (no `any` types unless necessary)

## Commit & Pull Request Guidelines

### Commit Message Format
- **Tense**: Present-tense, imperative mood
- **Length**: Subject line under 70 characters
- **Style**: Match existing commit history

Good examples:
```
Add error handling for cancelled Vercel deployments
Update ChatLog component with loading states
Fix database migration for user authentication
Refactor API routes to use dependency injection
```

Bad examples:
```
Fixed a bug
Updated stuff
WIP
changes
```

### Commit Message Body
Add a body when:
- Changes span multiple areas (API + UI)
- Complex refactoring requires explanation
- Breaking changes need migration instructions

Format:
```
Add Supabase integration for production database

- Configure connection pooling for performance
- Add migration script in scripts/migrate-to-supabase.js
- Update environment variable documentation

Breaking change: Requires SUPABASE_URL and SUPABASE_KEY in .env
```

### Pull Request Requirements

Every PR must include:

1. **Description**: Explain what changed and why
2. **User Impact**: Describe user-facing changes
3. **Verification Steps**: 
   - List commands run (`npm run build`, `curl /health`)
   - Describe manual testing performed
4. **Visual Changes**: Attach screenshots or Loom video for UI changes
5. **Issue Links**: Reference related issues with `Fixes #123` or `Relates to #456`
6. **Breaking Changes**: Explicitly call out breaking changes
7. **Database Changes**: Document any manual migration steps needed

### PR Template
```markdown
## What Changed
Brief description of changes

## Why
Reason for the change (bug fix, feature request, refactor, etc.)

## Verification
- [ ] `npm run build --workspace apps/web` passes
- [ ] `curl http://localhost:8080/health` returns 200
- [ ] Tested in browser at http://localhost:3000
- [ ] [Additional verification steps]

## Screenshots/Video
[Attach if UI changes]

## Related Issues
Fixes #123

## Breaking Changes
None / [Describe breaking changes]

## Migration Steps
None / [List manual steps needed]
```

## Error Handling and Debugging

### Common Issues and Solutions

**Port Already in Use**
- Check `.env` file for assigned ports
- Ports auto-detect and update in `.env`

**Installation Failures**
```bash
npm run clean
npm install
```

**Python Environment Issues**
```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Database Corruption**
```bash
npm run db:backup  # Backup current state
npm run db:reset   # Reset to fresh state
```

### Debugging Workflow

When encountering errors:
1. **Read the Error**: Don't skip error messages
2. **Check Logs**: Look at terminal output for both API and web servers
3. **Verify Environment**: Ensure `.env` file exists with correct values
4. **Check Dependencies**: Run `npm install` if packages seem missing
5. **Isolate the Problem**: Test API and frontend separately
6. **Search Existing Code**: Look for similar implementations
7. **Ask for Clarification**: If requirements are unclear, ask before implementing

## Multi-Step Development Patterns

### Feature Implementation Workflow
```
1. Understand requirement
   └─ Read issue/ticket description
   └─ Ask clarifying questions if needed

2. Review existing code
   └─ Search for similar features
   └─ Check component patterns in apps/web/components/
   └─ Review API patterns in apps/api/app/api/

3. Plan implementation
   └─ Identify files to modify
   └─ Consider database changes
   └─ Outline steps

4. Implement incrementally
   └─ Start with backend if data changes needed
   └─ Add frontend components
   └─ Test after each major change

5. Test thoroughly
   └─ Run build command
   └─ Test in browser
   └─ Check API responses

6. Document changes
   └─ Update comments if complex
   └─ Note any environment changes needed
   └─ Prepare PR description
```

### Bug Fix Workflow
```
1. Reproduce the bug
   └─ Follow steps to trigger issue
   └─ Note error messages

2. Identify root cause
   └─ Check logs
   └─ Add debug logging if needed
   └─ Use browser dev tools

3. Plan fix
   └─ Determine minimal change needed
   └─ Consider edge cases

4. Implement fix
   └─ Make targeted changes
   └─ Avoid refactoring unless necessary

5. Verify fix
   └─ Reproduce original bug scenario
   └─ Confirm fix works
   └─ Check for regressions

6. Add prevention
   └─ Consider adding test
   └─ Improve error messages if relevant
```

### Refactoring Workflow
```
1. Ensure tests exist
   └─ Manual test steps documented
   └─ Automated tests if available

2. Make small changes
   └─ One logical change at a time
   └─ Commit after each successful change

3. Test continuously
   └─ Run build after each change
   └─ Verify functionality maintained

4. Document reasoning
   └─ Explain why refactor was needed
   └─ Note any behavior changes
```

## Integration Patterns

### GitHub Integration
- Token from: https://github.com/settings/tokens
- Scope needed: `repo`
- Location: Settings → Service Integrations → GitHub

### Vercel Deployment
- Token from: https://vercel.com/account/tokens
- Location: Settings → Service Integrations → Vercel
- Automatic deployment on push when connected

### Supabase Database
- Credentials: https://supabase.com/dashboard → Project → Settings → API
- Project URL format: `https://xxxxx.supabase.co`
- Keys needed: Anon key (client), Service role key (server)

## AI Agent Best Practices

When working with AI coding agents (Claude Code, Cursor CLI, etc.):

### Effective Prompting
- Be specific about what needs to change
- Reference file paths explicitly
- Provide context about existing patterns
- Ask for explanations when code is unclear

### Tool Usage
- Use file search before creating similar components
- Read related files for context
- Execute commands through provided npm scripts
- Verify changes work before moving on

### Iterative Development
- Make one logical change at a time
- Test each change before continuing
- Ask for review if uncertain about approach
- Document decisions in commit messages

### Context Management
- Don't try to load entire codebase at once
- Focus on relevant files for current task
- Reference documentation when available
- Ask questions rather than making assumptions

---

*This document should evolve as the project grows. Update it when patterns change or new conventions are established.*
