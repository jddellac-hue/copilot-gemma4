# Best Practices

Guide des meilleures pratiques de développement pour React, TypeScript, Performance, et qualité de code.

## Table of Contents
1. [React Best Practices](#react-best-practices)
2. [TypeScript Best Practices](#typescript-best-practices)
3. [Performance Optimization](#performance-optimization)
4. [Code Quality](#code-quality)
5. [Security](#security)
6. [Error Handling](#error-handling)

---

## React Best Practices

### Component Design

#### 1. Component Composition over Props Drilling

```typescript
// ❌ BAD: Props drilling
function App() {
  const user = useUser();
  return <Dashboard user={user} />;
}

function Dashboard({ user }) {
  return <Sidebar user={user} />;
}

function Sidebar({ user }) {
  return <Profile user={user} />;
}

// ✅ GOOD: Context API
const UserContext = createContext();

function App() {
  const user = useUser();
  return (
    <UserContext.Provider value={user}>
      <Dashboard />
    </UserContext.Provider>
  );
}

function Profile() {
  const user = useContext(UserContext);
  return <div>{user.name}</div>;
}
```

#### 2. Small, Focused Components

```typescript
// ❌ BAD: Monolithic component
function UserDashboard() {
  return (
    <div>
      <header>{/* 50 lines */}</header>
      <nav>{/* 30 lines */}</nav>
      <main>{/* 100 lines */}</main>
      <footer>{/* 20 lines */}</footer>
    </div>
  );
}

// ✅ GOOD: Composed components
function UserDashboard() {
  return (
    <div>
      <Header />
      <Navigation />
      <MainContent />
      <Footer />
    </div>
  );
}
```

#### 3. Custom Hooks for Logic Reuse

```typescript
// ✅ GOOD: Extract logic into hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// Usage
function SearchComponent() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 500);

  useEffect(() => {
    if (debouncedQuery) {
      fetchResults(debouncedQuery);
    }
  }, [debouncedQuery]);
}
```

### State Management

#### 1. useEffect Dependencies

```typescript
// ❌ BAD: Missing dependencies
useEffect(() => {
  fetchData(userId);
}, []); // userId not in deps!

// ✅ GOOD: Complete dependencies
useEffect(() => {
  fetchData(userId);
}, [userId]);

// ✅ GOOD: Avoid dependencies with useRef
const userIdRef = useRef(userId);
useEffect(() => {
  userIdRef.current = userId;
}, [userId]);

useEffect(() => {
  // Use userIdRef.current - stable reference
  const interval = setInterval(() => {
    fetchData(userIdRef.current);
  }, 5000);
  return () => clearInterval(interval);
}, []); // Empty deps OK
```

#### 2. useState vs useRef

```typescript
// Use useState for render-triggering state
const [count, setCount] = useState(0);

// Use useRef for values that don't affect rendering
const timerId = useRef<NodeJS.Timeout>();
const previousValue = useRef(initialValue);

// Use useRef for DOM references
const inputRef = useRef<HTMLInputElement>(null);
```

#### 3. State Initialization

```typescript
// ❌ BAD: Expensive computation on every render
function Component() {
  const [data, setData] = useState(expensiveComputation());
}

// ✅ GOOD: Lazy initialization
function Component() {
  const [data, setData] = useState(() => expensiveComputation());
}

// ✅ GOOD: Load from localStorage
function Component() {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('user');
    return saved ? JSON.parse(saved) : null;
  });
}
```

### Performance Hooks

#### 1. useMemo for Expensive Calculations

```typescript
// ❌ BAD: Recalculate on every render
function Component({ items }) {
  const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
  // ...
}

// ✅ GOOD: Memoize expensive calculation
function Component({ items }) {
  const sortedItems = useMemo(
    () => items.sort((a, b) => a.name.localeCompare(b.name)),
    [items]
  );
  // ...
}
```

#### 2. useCallback for Function Stability

```typescript
// ❌ BAD: New function on every render
function Parent() {
  const handleClick = () => console.log('clicked');
  return <Child onClick={handleClick} />;
}

// ✅ GOOD: Stable function reference
function Parent() {
  const handleClick = useCallback(() => {
    console.log('clicked');
  }, []);
  return <Child onClick={handleClick} />;
}

// ✅ EVEN BETTER: Only if Child is memoized
const Child = memo(({ onClick }) => {
  return <button onClick={onClick}>Click</button>;
});
```

#### 3. React.memo for Component Memoization

```typescript
// ✅ GOOD: Prevent unnecessary re-renders
const ExpensiveComponent = memo(({ data }) => {
  // Complex rendering logic
  return <div>{/* ... */}</div>;
});

// ✅ GOOD: Custom comparison
const UserCard = memo(
  ({ user }) => <div>{user.name}</div>,
  (prevProps, nextProps) => prevProps.user.id === nextProps.user.id
);
```

### Side Effects

#### 1. Cleanup in useEffect

```typescript
// ✅ GOOD: Always cleanup
useEffect(() => {
  const subscription = api.subscribe(data => setData(data));

  return () => {
    subscription.unsubscribe(); // Cleanup!
  };
}, []);

// ✅ GOOD: Cleanup timers
useEffect(() => {
  const timer = setTimeout(() => setShow(false), 3000);

  return () => clearTimeout(timer);
}, []);

// ✅ GOOD: Cleanup event listeners
useEffect(() => {
  const handleResize = () => setWidth(window.innerWidth);
  window.addEventListener('resize', handleResize);

  return () => window.removeEventListener('resize', handleResize);
}, []);
```

#### 2. Conditional Effects

```typescript
// ✅ GOOD: Skip unnecessary effects
useEffect(() => {
  if (!userId) return; // Skip if no userId

  fetchUserData(userId);
}, [userId]);

// ✅ GOOD: Abort controller for fetch
useEffect(() => {
  const controller = new AbortController();

  fetch(url, { signal: controller.signal })
    .then(res => res.json())
    .then(data => setData(data))
    .catch(err => {
      if (err.name !== 'AbortError') {
        console.error(err);
      }
    });

  return () => controller.abort();
}, [url]);
```

---

## TypeScript Best Practices

### Type Safety

#### 1. Strong Typing Over 'any'

```typescript
// ❌ BAD: any type
function processData(data: any) {
  return data.map((item: any) => item.value);
}

// ✅ GOOD: Proper interfaces
interface DataItem {
  id: string;
  value: number;
}

function processData(data: DataItem[]): number[] {
  return data.map(item => item.value);
}
```

#### 2. Type Guards

```typescript
// ✅ GOOD: Type narrowing
interface Cat {
  meow(): void;
}

interface Dog {
  bark(): void;
}

type Pet = Cat | Dog;

function isCat(pet: Pet): pet is Cat {
  return (pet as Cat).meow !== undefined;
}

function makeSound(pet: Pet) {
  if (isCat(pet)) {
    pet.meow(); // TypeScript knows it's a Cat
  } else {
    pet.bark(); // TypeScript knows it's a Dog
  }
}
```

#### 3. Optional Chaining & Nullish Coalescing

```typescript
// ❌ BAD: Unsafe access
const userName = user.profile.name;

// ✅ GOOD: Safe access
const userName = user?.profile?.name ?? 'Unknown';

// ✅ GOOD: vs ||
const port = process.env.PORT ?? 3000;  // Use ?? (0 is falsy but valid)
const name = user.name || 'Guest';      // Use || (empty string should be 'Guest')
```

### Interfaces vs Types

#### When to Use Each

```typescript
// Use interface for object shapes (extendable)
interface User {
  id: string;
  name: string;
}

interface Admin extends User {
  permissions: string[];
}

// Use type for unions, intersections, primitives
type ID = string | number;
type Result = Success | Error;
type Point = { x: number; y: number };
```

### Generics

```typescript
// ✅ GOOD: Generic function
function first<T>(array: T[]): T | undefined {
  return array[0];
}

const num = first([1, 2, 3]); // number | undefined
const str = first(['a', 'b']); // string | undefined

// ✅ GOOD: Generic component
interface Props<T> {
  items: T[];
  renderItem: (item: T) => React.ReactNode;
}

function List<T>({ items, renderItem }: Props<T>) {
  return <ul>{items.map(renderItem)}</ul>;
}

// Usage
<List
  items={users}
  renderItem={user => <li key={user.id}>{user.name}</li>}
/>
```

### Utility Types

```typescript
interface User {
  id: string;
  name: string;
  email: string;
  password: string;
}

// Partial - all properties optional
type PartialUser = Partial<User>;

// Required - all properties required
type RequiredUser = Required<User>;

// Pick - select specific properties
type UserPreview = Pick<User, 'id' | 'name'>;

// Omit - exclude specific properties
type SafeUser = Omit<User, 'password'>;

// Record - map keys to type
type UserMap = Record<string, User>;

// ReturnType - extract return type
function getUser() {
  return { id: '1', name: 'Alice' };
}
type User = ReturnType<typeof getUser>;
```

---

## Performance Optimization

### Module-Level Caching

```typescript
// ✅ GOOD: Cache outside component
const cache = {
  data: null as Data | null,
  timestamp: 0,
  isValid() {
    return this.data && Date.now() - this.timestamp < 60000; // 1min
  }
};

function Component() {
  const [data, setData] = useState(() => cache.data);

  useEffect(() => {
    if (cache.isValid()) {
      return; // Use cached data
    }

    fetchData().then(result => {
      cache.data = result;
      cache.timestamp = Date.now();
      setData(result);
    });
  }, []);
}
```

### Lazy Loading

#### 1. Code Splitting

```typescript
// ✅ GOOD: Lazy load routes
import { lazy, Suspense } from 'react';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));

function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Suspense>
  );
}
```

#### 2. Data Lazy Loading

```typescript
// ✅ GOOD: Load on demand
function Component() {
  const [details, setDetails] = useState(null);
  const [showDetails, setShowDetails] = useState(false);

  const loadDetails = async () => {
    if (!details) {
      const data = await fetchDetails();
      setDetails(data);
    }
    setShowDetails(true);
  };

  return (
    <div>
      <button onClick={loadDetails}>Show Details</button>
      {showDetails && details && <Details data={details} />}
    </div>
  );
}
```

### Debouncing & Throttling

```typescript
// ✅ GOOD: Debounce user input
import { debounce } from 'lodash';

function SearchInput() {
  const debouncedSearch = useMemo(
    () => debounce((query: string) => {
      fetchResults(query);
    }, 500),
    []
  );

  useEffect(() => {
    return () => debouncedSearch.cancel();
  }, [debouncedSearch]);

  return (
    <input onChange={(e) => debouncedSearch(e.target.value)} />
  );
}

// ✅ GOOD: Throttle scroll events
import { throttle } from 'lodash';

function ScrollTracker() {
  useEffect(() => {
    const handleScroll = throttle(() => {
      console.log('Scrolled!');
    }, 100);

    window.addEventListener('scroll', handleScroll);
    return () => {
      window.removeEventListener('scroll', handleScroll);
      handleScroll.cancel();
    };
  }, []);
}
```

### List Virtualization

```typescript
// ✅ GOOD: Virtualize long lists
import { FixedSizeList } from 'react-window';

function VirtualList({ items }) {
  const Row = ({ index, style }) => (
    <div style={style}>
      {items[index].name}
    </div>
  );

  return (
    <FixedSizeList
      height={600}
      itemCount={items.length}
      itemSize={50}
      width="100%"
    >
      {Row}
    </FixedSizeList>
  );
}
```

---

## Code Quality

### ESLint Configuration

**.eslintrc.json**:
```json
{
  "extends": [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
    "plugin:@typescript-eslint/recommended"
  ],
  "rules": {
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/explicit-function-return-type": "warn",
    "no-console": ["warn", { "allow": ["warn", "error"] }],
    "prefer-const": "error",
    "no-var": "error"
  }
}
```

### Code Documentation

```typescript
/**
 * Fetches user data from the API
 *
 * @param userId - The unique identifier of the user
 * @param options - Optional fetch configuration
 * @returns Promise resolving to User object
 * @throws {NotFoundError} When user doesn't exist
 * @throws {NetworkError} When request fails
 *
 * @example
 * ```typescript
 * const user = await fetchUser('123');
 * console.log(user.name);
 * ```
 */
async function fetchUser(
  userId: string,
  options?: FetchOptions
): Promise<User> {
  // Implementation
}
```

### Code Review Checklist

**Before Submitting PR**:
- [ ] Code follows project style guide
- [ ] All functions have clear names and purpose
- [ ] Complex logic has comments explaining "why"
- [ ] No console.log left in code
- [ ] No commented-out code
- [ ] TypeScript strict mode errors resolved
- [ ] ESLint warnings addressed
- [ ] Tests added/updated
- [ ] Documentation updated

**Reviewer Checklist**:
- [ ] Logic is clear and correct
- [ ] Edge cases handled
- [ ] Error handling appropriate
- [ ] Performance implications considered
- [ ] Security implications considered
- [ ] Tests cover new functionality
- [ ] Code is maintainable

---

## Security

### Input Validation

```typescript
// ✅ GOOD: Validate user input
function updateEmail(email: string) {
  if (!email || !email.includes('@')) {
    throw new Error('Invalid email');
  }

  // Additional validation with library
  if (!isEmail(email)) {
    throw new Error('Invalid email format');
  }

  // Proceed with update
}
```

### XSS Prevention

```typescript
// ❌ BAD: dangerouslySetInnerHTML
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// ✅ GOOD: Let React escape content
<div>{userInput}</div>

// ✅ GOOD: If HTML needed, sanitize
import DOMPurify from 'dompurify';

<div dangerouslySetInnerHTML={{
  __html: DOMPurify.sanitize(userInput)
}} />
```

### Authentication Tokens

```typescript
// ✅ GOOD: Store in httpOnly cookie (server-side)
// NOT in localStorage (XSS vulnerable)

// ✅ GOOD: Include in requests
const response = await fetch('/api/data', {
  headers: {
    'Authorization': `Bearer ${token}`,
  },
  credentials: 'include', // Include cookies
});
```

### Environment Variables

```typescript
// ✅ GOOD: Use env variables for secrets
const apiKey = process.env.REACT_APP_API_KEY;

// ❌ BAD: Hard-coded secrets
const apiKey = 'sk_live_abc123'; // Never do this!

// ✅ GOOD: Validate required env vars
if (!process.env.REACT_APP_API_KEY) {
  throw new Error('Missing required environment variable: REACT_APP_API_KEY');
}
```

---

## Error Handling

### Try-Catch Patterns

```typescript
// ✅ GOOD: Specific error handling
async function fetchData() {
  try {
    const response = await fetch('/api/data');

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    if (error instanceof TypeError) {
      // Network error
      console.error('Network error:', error);
      throw new NetworkError('Failed to connect to server');
    } else if (error instanceof SyntaxError) {
      // JSON parse error
      console.error('Invalid JSON:', error);
      throw new DataError('Invalid response from server');
    } else {
      // Other errors
      console.error('Unexpected error:', error);
      throw error;
    }
  }
}
```

### Error Boundaries

```typescript
// ✅ GOOD: Catch React errors
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error?: Error }
> {
  state = { hasError: false, error: undefined };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
    // Log to error tracking service
  }

  render() {
    if (this.state.hasError) {
      return (
        <div>
          <h1>Something went wrong</h1>
          <details>
            <summary>Error details</summary>
            <pre>{this.state.error?.message}</pre>
          </details>
        </div>
      );
    }

    return this.props.children;
  }
}

// Usage
<ErrorBoundary>
  <App />
</ErrorBoundary>
```

### User-Friendly Error Messages

```typescript
// ✅ GOOD: Translate errors for users
function getErrorMessage(error: Error): string {
  if (error instanceof NetworkError) {
    return 'Unable to connect. Please check your internet connection.';
  }

  if (error instanceof AuthError) {
    return 'Your session has expired. Please log in again.';
  }

  if (error instanceof ValidationError) {
    return error.message; // Already user-friendly
  }

  // Fallback
  return 'An unexpected error occurred. Please try again.';
}

// Usage
try {
  await fetchData();
} catch (error) {
  toast.error(getErrorMessage(error as Error));
}
```

---

**Version**: 1.0.0
**Last Updated**: January 2, 2026
