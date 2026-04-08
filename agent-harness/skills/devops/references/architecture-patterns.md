# Architecture Patterns

Patterns architecturaux éprouvés et réutilisables pour applications modernes.

## Table of Contents
1. [Project Structure](#project-structure)
2. [Component Architecture](#component-architecture)
3. [State Management](#state-management)
4. [API Layer](#api-layer)
5. [Type System Organization](#type-system-organization)
6. [Module Patterns](#module-patterns)
7. [Performance Patterns](#performance-patterns)

---

## Project Structure

### Standard Frontend Structure

```
project-root/
├── public/                     # Static assets
│   ├── index.html
│   ├── favicon.ico
│   └── assets/
│       ├── images/
│       └── fonts/
│
├── src/                        # Source code
│   ├── app/                    # Application root
│   │   ├── App.tsx             # Main component
│   │   ├── App.css
│   │   └── routes.tsx          # Route definitions
│   │
│   ├── pages/                  # Page components (routed)
│   │   ├── Home/
│   │   │   ├── Home.tsx
│   │   │   └── Home.css
│   │   ├── Dashboard/
│   │   └── Settings/
│   │
│   ├── components/             # Reusable components
│   │   ├── common/             # Shared across app
│   │   │   ├── Button/
│   │   │   ├── Modal/
│   │   │   └── Tooltip/
│   │   ├── layout/             # Layout components
│   │   │   ├── Header/
│   │   │   ├── Sidebar/
│   │   │   └── Footer/
│   │   └── features/           # Feature-specific
│   │       ├── UserProfile/
│   │       └── Analytics/
│   │
│   ├── hooks/                  # Custom React hooks
│   │   ├── useAuth.ts
│   │   ├── useApi.ts
│   │   └── useLocalStorage.ts
│   │
│   ├── services/               # Business logic & API
│   │   ├── api/
│   │   │   ├── client.ts       # API client config
│   │   │   ├── auth.ts         # Auth endpoints
│   │   │   └── users.ts        # User endpoints
│   │   └── analytics.ts        # Analytics service
│   │
│   ├── types/                  # TypeScript definitions
│   │   ├── api.ts              # API types
│   │   ├── models.ts           # Data models
│   │   └── enums.ts            # Enums
│   │
│   ├── utils/                  # Utility functions
│   │   ├── format.ts           # Formatting
│   │   ├── validation.ts       # Validators
│   │   └── helpers.ts          # Generic helpers
│   │
│   ├── constants/              # Constants
│   │   ├── routes.ts
│   │   ├── config.ts
│   │   └── api.ts
│   │
│   ├── context/                # React Context
│   │   ├── AuthContext.tsx
│   │   └── ThemeContext.tsx
│   │
│   ├── store/                  # State management (Redux/Zustand)
│   │   ├── index.ts
│   │   ├── slices/
│   │   │   ├── userSlice.ts
│   │   │   └── appSlice.ts
│   │   └── middleware/
│   │
│   ├── styles/                 # Global styles
│   │   ├── global.css
│   │   ├── variables.css
│   │   └── themes/
│   │
│   └── main.tsx                # Entry point
│
├── tests/                      # Tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── .claude/                    # Claude Code skills
│   └── skills/
│
├── .github/                    # GitHub config
│   └── workflows/
│
├── .husky/                     # Git hooks
│
├── app.config.json             # App configuration
├── package.json
├── tsconfig.json
├── vite.config.ts              # Build tool config
├── .eslintrc.json
└── .prettierrc
```

### Backend/API Structure

```
api/                            # Backend functions
├── auth/
│   ├── login.function.ts
│   ├── logout.function.ts
│   └── refresh.function.ts
│
├── users/
│   ├── getUser.function.ts
│   ├── updateUser.function.ts
│   └── deleteUser.function.ts
│
├── shared/                     # Shared utilities
│   ├── validators.ts
│   ├── middleware.ts
│   └── errors.ts
│
└── types/                      # Shared types
    ├── requests.ts
    └── responses.ts
```

---

## Component Architecture

### Container/Presentational Pattern

**Container** (logic):
```typescript
// containers/UserProfileContainer.tsx
function UserProfileContainer() {
  const { user, loading, error } = useUser();
  const { updateUser } = useUserActions();

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} />;

  return <UserProfile user={user} onUpdate={updateUser} />;
}
```

**Presentational** (UI):
```typescript
// components/UserProfile.tsx
interface Props {
  user: User;
  onUpdate: (user: User) => void;
}

function UserProfile({ user, onUpdate }: Props) {
  return (
    <div className="user-profile">
      <h1>{user.name}</h1>
      <button onClick={() => onUpdate({ ...user, name: 'New Name' })}>
        Update
      </button>
    </div>
  );
}
```

### Compound Components Pattern

```typescript
// components/Tabs/Tabs.tsx
interface TabsContextValue {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function Tabs({ children, defaultTab }: { children: React.ReactNode; defaultTab: string }) {
  const [activeTab, setActiveTab] = useState(defaultTab);

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className="tabs">{children}</div>
    </TabsContext.Provider>
  );
}

function TabList({ children }: { children: React.ReactNode }) {
  return <div className="tab-list">{children}</div>;
}

function Tab({ id, children }: { id: string; children: React.ReactNode }) {
  const { activeTab, setActiveTab } = useContext(TabsContext)!;
  const isActive = activeTab === id;

  return (
    <button
      className={`tab ${isActive ? 'active' : ''}`}
      onClick={() => setActiveTab(id)}
    >
      {children}
    </button>
  );
}

function TabPanel({ id, children }: { id: string; children: React.ReactNode }) {
  const { activeTab } = useContext(TabsContext)!;
  if (activeTab !== id) return null;

  return <div className="tab-panel">{children}</div>;
}

// Export as compound component
Tabs.List = TabList;
Tabs.Tab = Tab;
Tabs.Panel = TabPanel;

export { Tabs };

// Usage
<Tabs defaultTab="profile">
  <Tabs.List>
    <Tabs.Tab id="profile">Profile</Tabs.Tab>
    <Tabs.Tab id="settings">Settings</Tabs.Tab>
  </Tabs.List>

  <Tabs.Panel id="profile">
    <UserProfile />
  </Tabs.Panel>

  <Tabs.Panel id="settings">
    <Settings />
  </Tabs.Panel>
</Tabs>
```

### Render Props Pattern

```typescript
// components/DataFetcher.tsx
interface Props<T> {
  url: string;
  children: (data: {
    data: T | null;
    loading: boolean;
    error: Error | null;
  }) => React.ReactNode;
}

function DataFetcher<T>({ url, children }: Props<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    fetch(url)
      .then(res => res.json())
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [url]);

  return <>{children({ data, loading, error })}</>;
}

// Usage
<DataFetcher<User> url="/api/user/123">
  {({ data, loading, error }) => {
    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error: {error.message}</div>;
    if (!data) return null;
    return <div>{data.name}</div>;
  }}
</DataFetcher>
```

---

## State Management

### State Management Layers

```
┌─────────────────────────────────────┐
│  1. Local State (useState)          │ ← Component-specific
├─────────────────────────────────────┤
│  2. Lifted State (props)            │ ← Shared between siblings
├─────────────────────────────────────┤
│  3. Context API                     │ ← Subtree-wide state
├─────────────────────────────────────┤
│  4. Module Cache                    │ ← Persist across unmount
├─────────────────────────────────────┤
│  5. LocalStorage/SessionStorage     │ ← Persist across sessions
├─────────────────────────────────────┤
│  6. External Store (Redux/Zustand)  │ ← Complex global state
└─────────────────────────────────────┘
```

### Module-Level Cache Pattern

```typescript
// services/userService.ts

// Module-level cache (outside React)
const cache = {
  users: new Map<string, User>(),
  timestamp: new Map<string, number>(),

  get(id: string): User | null {
    const user = this.users.get(id);
    const timestamp = this.timestamp.get(id);

    if (!user || !timestamp) return null;

    // Cache valid for 5 minutes
    if (Date.now() - timestamp > 5 * 60 * 1000) {
      this.users.delete(id);
      this.timestamp.delete(id);
      return null;
    }

    return user;
  },

  set(id: string, user: User): void {
    this.users.set(id, user);
    this.timestamp.set(id, Date.now());
  },

  clear(): void {
    this.users.clear();
    this.timestamp.clear();
  },
};

export async function fetchUser(id: string): Promise<User> {
  // Check cache first
  const cached = cache.get(id);
  if (cached) return cached;

  // Fetch from API
  const response = await fetch(`/api/users/${id}`);
  const user = await response.json();

  // Cache result
  cache.set(id, user);

  return user;
}

// Hook to use cached service
export function useUser(id: string) {
  const [user, setUser] = useState<User | null>(() => cache.get(id));
  const [loading, setLoading] = useState(!user);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    fetchUser(id)
      .then(setUser)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [id]);

  return { user, loading, error };
}
```

### Context Pattern with Custom Hook

```typescript
// context/AuthContext.tsx
interface AuthContextValue {
  user: User | null;
  login: (credentials: Credentials) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const saved = localStorage.getItem('user');
    return saved ? JSON.parse(saved) : null;
  });

  const login = async (credentials: Credentials) => {
    const user = await api.login(credentials);
    setUser(user);
    localStorage.setItem('user', JSON.stringify(user));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('user');
  };

  const value = {
    user,
    login,
    logout,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Custom hook for consuming context
export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }

  return context;
}

// Usage
function App() {
  return (
    <AuthProvider>
      <Router />
    </AuthProvider>
  );
}

function LoginButton() {
  const { login, isAuthenticated } = useAuth();
  // ...
}
```

---

## API Layer

### API Client Pattern

```typescript
// services/api/client.ts
class ApiClient {
  private baseURL: string;
  private defaultHeaders: Record<string, string>;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
  }

  setAuthToken(token: string) {
    this.defaultHeaders['Authorization'] = `Bearer ${token}`;
  }

  async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;
    const config: RequestInit = {
      ...options,
      headers: {
        ...this.defaultHeaders,
        ...options.headers,
      },
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      throw new ApiError(response.status, await response.text());
    }

    return response.json();
  }

  get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  post<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  put<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }
}

export const apiClient = new ApiClient('/api');

// services/api/users.ts
export const usersApi = {
  getUser: (id: string) => apiClient.get<User>(`/users/${id}`),
  updateUser: (id: string, data: Partial<User>) =>
    apiClient.put<User>(`/users/${id}`, data),
  deleteUser: (id: string) => apiClient.delete<void>(`/users/${id}`),
};
```

### Repository Pattern

```typescript
// repositories/UserRepository.ts
export class UserRepository {
  async findById(id: string): Promise<User | null> {
    try {
      return await apiClient.get<User>(`/users/${id}`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  }

  async findAll(): Promise<User[]> {
    return apiClient.get<User[]>('/users');
  }

  async create(userData: CreateUserDto): Promise<User> {
    return apiClient.post<User>('/users', userData);
  }

  async update(id: string, userData: UpdateUserDto): Promise<User> {
    return apiClient.put<User>(`/users/${id}`, userData);
  }

  async delete(id: string): Promise<void> {
    return apiClient.delete<void>(`/users/${id}`);
  }
}

export const userRepository = new UserRepository();

// Usage in hook
export function useUser(id: string) {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    userRepository.findById(id).then(setUser);
  }, [id]);

  return user;
}
```

---

## Type System Organization

### Domain Models

```typescript
// types/models/User.ts
export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  createdAt: Date;
  updatedAt: Date;
}

export enum UserRole {
  Admin = 'ADMIN',
  User = 'USER',
  Guest = 'GUEST',
}

// types/models/Post.ts
export interface Post {
  id: string;
  title: string;
  content: string;
  authorId: string;
  author?: User; // Optional relation
  createdAt: Date;
}
```

### DTOs (Data Transfer Objects)

```typescript
// types/dto/CreateUserDto.ts
export interface CreateUserDto {
  email: string;
  name: string;
  password: string;
}

// types/dto/UpdateUserDto.ts
export interface UpdateUserDto {
  email?: string;
  name?: string;
}

// types/dto/UserResponseDto.ts
export interface UserResponseDto {
  id: string;
  email: string;
  name: string;
  role: string;
  // No password! Security
}
```

### API Types

```typescript
// types/api.ts
export interface ApiResponse<T> {
  data: T;
  message?: string;
  timestamp: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ApiError {
  status: number;
  message: string;
  errors?: Record<string, string[]>;
}
```

---

## Module Patterns

### Facade Pattern (Simplified Interface)

```typescript
// services/NotificationService.ts
class NotificationService {
  private emailService: EmailService;
  private smsService: SmsService;
  private pushService: PushService;

  constructor() {
    this.emailService = new EmailService();
    this.smsService = new SmsService();
    this.pushService = new PushService();
  }

  // Simplified interface
  async notify(user: User, message: string, channels: NotificationChannel[]) {
    const promises = channels.map(channel => {
      switch (channel) {
        case 'email':
          return this.emailService.send(user.email, message);
        case 'sms':
          return this.smsService.send(user.phone, message);
        case 'push':
          return this.pushService.send(user.deviceToken, message);
      }
    });

    await Promise.all(promises);
  }
}

export const notificationService = new NotificationService();

// Usage
notificationService.notify(user, 'Hello!', ['email', 'push']);
```

### Singleton Pattern (Single Instance)

```typescript
// services/Logger.ts
class Logger {
  private static instance: Logger;
  private logs: string[] = [];

  private constructor() {
    // Private constructor prevents instantiation
  }

  static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger();
    }
    return Logger.instance;
  }

  log(message: string) {
    const timestamp = new Date().toISOString();
    this.logs.push(`[${timestamp}] ${message}`);
    console.log(message);
  }

  getLogs(): string[] {
    return [...this.logs];
  }
}

export const logger = Logger.getInstance();
```

### Observer Pattern (Event System)

```typescript
// utils/EventEmitter.ts
type EventHandler<T = any> = (data: T) => void;

class EventEmitter {
  private events: Map<string, EventHandler[]> = new Map();

  on(event: string, handler: EventHandler): () => void {
    if (!this.events.has(event)) {
      this.events.set(event, []);
    }

    this.events.get(event)!.push(handler);

    // Return unsubscribe function
    return () => this.off(event, handler);
  }

  off(event: string, handler: EventHandler): void {
    const handlers = this.events.get(event);
    if (!handlers) return;

    const index = handlers.indexOf(handler);
    if (index !== -1) {
      handlers.splice(index, 1);
    }
  }

  emit(event: string, data?: any): void {
    const handlers = this.events.get(event);
    if (!handlers) return;

    handlers.forEach(handler => handler(data));
  }
}

export const eventBus = new EventEmitter();

// Usage
const unsubscribe = eventBus.on('user:login', (user) => {
  console.log('User logged in:', user);
});

eventBus.emit('user:login', { id: '1', name: 'Alice' });

unsubscribe(); // Cleanup
```

---

## Performance Patterns

### Lazy Load Images

```typescript
// components/LazyImage.tsx
function LazyImage({ src, alt, placeholder }: {
  src: string;
  alt: string;
  placeholder?: string;
}) {
  const [loaded, setLoaded] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    if (!imgRef.current) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          const img = imgRef.current!;
          img.src = src;
          img.onload = () => setLoaded(true);
          observer.disconnect();
        }
      },
      { rootMargin: '50px' }
    );

    observer.observe(imgRef.current);

    return () => observer.disconnect();
  }, [src]);

  return (
    <img
      ref={imgRef}
      alt={alt}
      src={placeholder || 'data:image/svg+xml,...'}
      className={loaded ? 'loaded' : 'loading'}
    />
  );
}
```

### Infinite Scroll Pattern

```typescript
// hooks/useInfiniteScroll.ts
export function useInfiniteScroll<T>(
  fetchMore: (page: number) => Promise<T[]>,
  options: { threshold?: number } = {}
) {
  const [data, setData] = useState<T[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  const loaderRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loaderRef.current || !hasMore) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !loading) {
          setLoading(true);
          fetchMore(page)
            .then(newData => {
              if (newData.length === 0) {
                setHasMore(false);
              } else {
                setData(prev => [...prev, ...newData]);
                setPage(p => p + 1);
              }
            })
            .finally(() => setLoading(false));
        }
      },
      { threshold: options.threshold ?? 0.1 }
    );

    observer.observe(loaderRef.current);

    return () => observer.disconnect();
  }, [page, loading, hasMore]);

  return { data, loading, hasMore, loaderRef };
}

// Usage
function UserList() {
  const { data: users, loading, hasMore, loaderRef } = useInfiniteScroll(
    (page) => fetch(`/api/users?page=${page}`).then(r => r.json())
  );

  return (
    <div>
      {users.map(user => <UserCard key={user.id} user={user} />)}
      {hasMore && <div ref={loaderRef}>Loading...</div>}
    </div>
  );
}
```

---

**Version**: 1.0.0
**Last Updated**: January 2, 2026
